import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  AlertCircle,
  Pause,
  DollarSign,
  Wrench,
  Shield,
  Check,
  ArrowRight,
  X,
  Loader2,
  Sparkles,
  HeartHandshake,
  TrendingDown,
  Layers,
  Database,
  Users,
  ShieldCheck,
  Rocket
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth, fetcher } from '@/lib/apiClient';
import useSWR from 'swr';

interface CancelSubscriptionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

interface DowngradeAuditData {
  status: string;
  current_active_campaigns: number;
  free_limit_campaigns: number;
  campaigns_to_archive_count: number;
  retained_campaign_name: string;
  archived_campaign_names: string[];
  current_accounts: number;
  free_limit_accounts: number;
  accounts_to_archive_count: number;
  retained_account_name: string;
  total_knowledge_assets: number;
  free_limit_knowledge_assets: number;
  assets_over_limit: number;
  data_loss_risk: boolean;
  guarantee_message: string;
}

export const CancelSubscriptionModal: React.FC<CancelSubscriptionModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [reason, setReason] = useState<string>('paused');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Downgrade audit query
  const { data: auditData, isLoading: isAuditLoading } = useSWR<DowngradeAuditData>(
    isOpen && step >= 3 ? '/api/elein/billing/downgrade-audit' : null,
    fetcher
  );

  useEffect(() => {
    if (isOpen) {
      setStep(1);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleApplyOffer = async (offerType: 'pause' | 'discount' | 'starter_downsell') => {
    setIsSubmitting(true);
    try {
      const res = await fetchWithAuth('/api/elein/billing/salvage-offer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offerType, reason }),
      });

      if (!res.ok) throw new Error("Failed to apply offer");

      if (offerType === 'pause') {
        toast.success("Account frozen for 30 days! All sequences and lead lists preserved with $0 billed.");
      } else if (offerType === 'starter_downsell') {
        toast.success("Switched to Solo Starter Tier! 1,500 credits added to your workspace.");
      } else {
        toast.success("50% discount voucher applied to your next billing cycle!");
      }

      if (onSuccess) onSuccess();
      onClose();
    } catch (err: any) {
      toast.error(err.message || "Failed to apply offer");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConfirmCancel = async () => {
    setIsSubmitting(true);
    try {
      const res = await fetchWithAuth('/api/elein/billing/cancel-subscription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });

      if (!res.ok) throw new Error("Failed to schedule cancellation");

      toast.info("Subscription marked for cancellation at period end. Your account will gracefully transition to Free Tier.");
      if (onSuccess) onSuccess();
      onClose();
    } catch (err: any) {
      toast.error(err.message || "Failed to cancel subscription");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 10 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-lg rounded-3xl bg-card border border-destructive/20 shadow-[0_0_50px_rgba(239,68,68,0.15)] p-6 md:p-8 text-foreground overflow-hidden"
      >
        <button
          onClick={onClose}
          className="absolute top-6 right-6 text-muted-foreground hover:text-foreground p-1.5 rounded-full hover:bg-muted/50 transition z-10"
        >
          <X size={18} />
        </button>

        {/* ─── STEP 1: Reason Survey ─── */}
        {step === 1 && (
          <div className="space-y-6 py-2">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-widest text-destructive">Subscription Management</span>
              <h2 className="text-2xl font-bold tracking-tight text-foreground mt-1">Before you cancel...</h2>
              <p className="text-xs text-muted-foreground mt-1.5">
                Help us understand why Growth Tier isn't working for your team right now.
              </p>
            </div>

            <div className="space-y-2.5">
              {[
                { id: 'paused', label: 'Taking a break from outreach', desc: 'Campaign finished or sales pipeline is currently full', icon: <Pause size={16} /> },
                { id: 'expensive', label: 'Too expensive for current budget', desc: 'Need a smaller, affordable solo plan', icon: <DollarSign size={16} /> },
                { id: 'low_replies', label: 'Low response rate or lead quality', desc: 'Need help optimizing sequence conversion', icon: <TrendingDown size={16} /> },
                { id: 'technical', label: 'Missing features or technical friction', desc: 'Encountered platform bugs or blockers', icon: <Wrench size={16} /> },
                { id: 'other', label: 'Other reasons', desc: 'No longer running LinkedIn automation', icon: <AlertCircle size={16} /> },
              ].map((opt) => (
                <div
                  key={opt.id}
                  onClick={() => setReason(opt.id)}
                  className={`p-3.5 rounded-2xl border cursor-pointer transition flex items-center justify-between ${
                    reason === opt.id
                      ? 'border-primary bg-primary/5 ring-1 ring-primary'
                      : 'border-border/60 bg-muted/20 hover:border-foreground/20'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-xl bg-background border border-border/50 text-foreground">
                      {opt.icon}
                    </div>
                    <div>
                      <div className="text-xs font-bold text-foreground">{opt.label}</div>
                      <div className="text-[11px] text-muted-foreground">{opt.desc}</div>
                    </div>
                  </div>
                  {reason === opt.id && <Check size={16} className="text-primary shrink-0" />}
                </div>
              ))}
            </div>

            <button
              onClick={() => setStep(2)}
              className="w-full py-3.5 px-4 rounded-xl bg-foreground text-background font-bold hover:opacity-90 transition flex items-center justify-center gap-2 text-sm"
            >
              <span>Continue</span>
              <ArrowRight size={16} />
            </button>
          </div>
        )}

        {/* ─── STEP 2: Tailored Salvage Offer / Downsell Ladder ─── */}
        {step === 2 && (
          <div className="space-y-6 py-2">
            {reason === 'expensive' ? (
              <div className="space-y-5 text-center">
                <div className="w-14 h-14 bg-emerald-500/10 text-emerald-400 rounded-2xl mx-auto flex items-center justify-center border border-emerald-500/20">
                  <Sparkles size={28} />
                </div>
                <div>
                  <h3 className="text-xl font-bold">Down-Tier to Solo Starter Plan?</h3>
                  <p className="text-xs text-muted-foreground mt-1.5 max-w-sm mx-auto leading-relaxed">
                    Keep outbound running at 68% lower cost. Switch to Solo Starter at ₹2,499 / $29/mo (includes 1,500 credits, 3 accounts, and full AI sequencing).
                  </p>
                </div>

                <div className="p-4 bg-muted/30 border border-border/60 rounded-2xl text-xs text-left space-y-2">
                  <div className="flex items-center gap-2 text-foreground font-medium">
                    <Check size={14} className="text-primary" />
                    <span>₹2,499 / mo instead of ₹7,999 (Save ₹5,500/mo)</span>
                  </div>
                  <div className="flex items-center gap-2 text-foreground font-medium">
                    <Check size={14} className="text-primary" />
                    <span>1,500 verified credits refreshed every month</span>
                  </div>
                  <div className="flex items-center gap-2 text-foreground font-medium">
                    <Check size={14} className="text-primary" />
                    <span>Zero data loss — all active sequences stay online</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <button
                    disabled={isSubmitting}
                    onClick={() => handleApplyOffer('starter_downsell')}
                    className="w-full py-3.5 bg-emerald-600 text-white font-bold rounded-xl hover:bg-emerald-500 transition shadow-lg text-sm flex items-center justify-center gap-2"
                  >
                    {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : "Switch to Solo Starter Plan (₹2,499/mo)"}
                  </button>

                  <button
                    disabled={isSubmitting}
                    onClick={() => handleApplyOffer('discount')}
                    className="w-full py-2.5 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-xl transition"
                  >
                    Or Take 50% Off Next Month (₹3,999)
                  </button>

                  <button
                    onClick={() => setStep(3)}
                    className="text-xs text-muted-foreground hover:text-foreground transition underline pt-2 block mx-auto"
                  >
                    No thanks, review Free Tier downgrade
                  </button>
                </div>
              </div>
            ) : reason === 'paused' ? (
              <div className="space-y-5 text-center">
                <div className="w-14 h-14 bg-indigo-500/10 text-indigo-400 rounded-2xl mx-auto flex items-center justify-center border border-indigo-500/20">
                  <Pause size={28} />
                </div>
                <div>
                  <h3 className="text-xl font-bold">Freeze Your Account for 30 Days?</h3>
                  <p className="text-xs text-muted-foreground mt-1.5 max-w-sm mx-auto leading-relaxed">
                    Keep all 20 workflows, prospect lead lists, and AI configurations 100% frozen with zero billing. Resume whenever you're ready with 1 click.
                  </p>
                </div>
                <div className="p-4 bg-muted/30 border border-border/60 rounded-2xl text-xs text-left space-y-2">
                  <div className="flex items-center gap-2 text-foreground font-medium">
                    <Check size={14} className="text-primary" />
                    <span>$0 charged for the next 30 days</span>
                  </div>
                  <div className="flex items-center gap-2 text-foreground font-medium">
                    <Check size={14} className="text-primary" />
                    <span>All sequence workflows and lead lists preserved</span>
                  </div>
                </div>
                <div className="space-y-2">
                  <button
                    disabled={isSubmitting}
                    onClick={() => handleApplyOffer('pause')}
                    className="w-full py-3.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 transition shadow-lg text-sm"
                  >
                    {isSubmitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : "Pause Account for 30 Days (Keep My Setup)"}
                  </button>
                  <button
                    onClick={() => setStep(3)}
                    className="text-xs text-muted-foreground hover:text-foreground transition underline pt-2 block mx-auto"
                  >
                    No thanks, review Free Tier downgrade
                  </button>
                </div>
              </div>
            ) : reason === 'low_replies' ? (
              <div className="space-y-5 text-center">
                <div className="w-14 h-14 bg-blue-500/10 text-blue-400 rounded-2xl mx-auto flex items-center justify-center border border-blue-500/20">
                  <Rocket size={28} />
                </div>
                <div>
                  <h3 className="text-xl font-bold">Let's Optimize Your Conversion</h3>
                  <p className="text-xs text-muted-foreground mt-1.5 max-w-sm mx-auto leading-relaxed">
                    Cold outreach requires precision targeting. Claim 50% off next month plus free Bayesian ICP tuning to turn low replies into booked meetings.
                  </p>
                </div>
                <div className="p-4 bg-muted/30 border border-border/60 rounded-2xl text-xs text-left space-y-2">
                  <div className="flex items-center gap-2 text-foreground font-medium">
                    <Check size={14} className="text-primary" />
                    <span>50% discount applied to your next billing cycle</span>
                  </div>
                  <div className="flex items-center gap-2 text-foreground font-medium">
                    <Check size={14} className="text-primary" />
                    <span>Free prompt review & sequence optimization</span>
                  </div>
                </div>
                <div className="space-y-2">
                  <button
                    disabled={isSubmitting}
                    onClick={() => handleApplyOffer('discount')}
                    className="w-full py-3.5 bg-blue-600 text-white font-bold rounded-xl hover:bg-blue-500 transition shadow-lg text-sm"
                  >
                    {isSubmitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : "Claim 50% Discount & Optimization"}
                  </button>
                  <button
                    onClick={() => setStep(3)}
                    className="text-xs text-muted-foreground hover:text-foreground transition underline pt-2 block mx-auto"
                  >
                    No thanks, review Free Tier downgrade
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-5 text-center">
                <div className="w-14 h-14 bg-indigo-500/10 text-indigo-400 rounded-2xl mx-auto flex items-center justify-center border border-indigo-500/20">
                  <HeartHandshake size={28} />
                </div>
                <div>
                  <h3 className="text-xl font-bold">Can We Fix It For You?</h3>
                  <p className="text-xs text-muted-foreground mt-1.5 max-w-sm mx-auto leading-relaxed">
                    Our founder personally reviews technical blockers. Let us resolve the friction or proceed to downgrade.
                  </p>
                </div>
                <div className="space-y-2">
                  <a
                    href="mailto:krdeeksha@gmail.com?subject=Ele-in Technical Assistance"
                    className="w-full py-3.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 transition shadow-lg text-sm block"
                  >
                    Talk Directly to Engineering
                  </a>
                  <button
                    onClick={() => setStep(3)}
                    className="text-xs text-muted-foreground hover:text-foreground transition underline pt-2 block mx-auto"
                  >
                    Continue to downgrade audit
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─── STEP 3: Downgrade Safety Impact Audit ─── */}
        {step === 3 && (
          <div className="space-y-5 py-2">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-widest text-amber-500">Downgrade Safety Clamp</span>
              <h3 className="text-xl font-bold text-foreground mt-0.5">Free Tier Transition Audit</h3>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                Review what happens when your plan expires. Ele-in enforces non-destructive archiving — zero data is ever deleted.
              </p>
            </div>

            {isAuditLoading ? (
              <div className="p-8 flex flex-col items-center justify-center space-y-2">
                <Loader2 size={24} className="animate-spin text-primary" />
                <span className="text-xs text-muted-foreground">Auditing workspace resources...</span>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-muted/20 border border-border/60 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <Layers size={14} className="text-indigo-500" /> Campaigns
                    </span>
                    <span className="font-mono text-muted-foreground text-[11px]">
                      {auditData?.current_active_campaigns || 0} Active → 1 Retained
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Campaign <strong className="text-foreground">"{auditData?.retained_campaign_name || 'Active Campaign'}"</strong> remains running. Excess campaigns are archived to read-only cold storage.
                  </p>
                </div>

                <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-muted/20 border border-border/60 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <Users size={14} className="text-blue-500" /> Senders
                    </span>
                    <span className="font-mono text-muted-foreground text-[11px]">
                      {auditData?.current_accounts || 1} Connected → 1 Retained
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Primary account <strong className="text-foreground">"{auditData?.retained_account_name || 'Primary Senders'}"</strong> stays connected.
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-2.5">
                  <ShieldCheck size={16} className="text-emerald-500 shrink-0 mt-0.5" />
                  <p className="text-[11px] text-emerald-800 dark:text-emerald-300 leading-relaxed font-medium">
                    {auditData?.guarantee_message || "Zero data is ever deleted. Workflows and leads are safely preserved."}
                  </p>
                </div>
              </div>
            )}

            <div className="flex items-center gap-2 pt-2">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="w-1/3 py-3 rounded-xl text-xs font-semibold border border-border hover:bg-muted transition"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => setStep(4)}
                className="w-2/3 py-3 rounded-xl text-xs font-bold bg-foreground text-background hover:opacity-90 transition flex items-center justify-center gap-1.5"
              >
                <span>Proceed to Confirm</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ─── STEP 4: Final Confirmation ─── */}
        {step === 4 && (
          <div className="space-y-6 py-2 text-center">
            <div className="w-14 h-14 bg-destructive/10 text-destructive rounded-2xl mx-auto flex items-center justify-center border border-destructive/20">
              <Shield size={28} />
            </div>
            <div>
              <h3 className="text-xl font-bold text-foreground">Confirm Cancellation</h3>
              <p className="text-xs text-muted-foreground mt-1.5 max-w-sm mx-auto leading-relaxed">
                Your Growth Tier benefits remain active until the end of your billing cycle. After that, your workspace transitions gracefully to Free Tier without data deletion.
              </p>
            </div>

            <div className="p-4 bg-muted/20 border border-border/50 rounded-2xl text-xs text-left space-y-2 text-muted-foreground">
              <div>• No immediate cutoff — access continues through period end</div>
              <div>• Excess campaigns archived safely to cold storage</div>
              <div>• 1-click reactivation available at any time before expiration</div>
            </div>

            <div className="space-y-2">
              <button
                disabled={isSubmitting}
                onClick={handleConfirmCancel}
                className="w-full py-3.5 bg-destructive text-destructive-foreground font-bold rounded-xl hover:bg-destructive/90 disabled:opacity-50 transition shadow-lg text-sm"
              >
                {isSubmitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : "Confirm Downgrade to Free Tier"}
              </button>
              <button
                onClick={onClose}
                className="text-xs text-foreground font-bold hover:underline pt-2 block mx-auto"
              >
                Never mind, keep my Growth Plan
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
};
