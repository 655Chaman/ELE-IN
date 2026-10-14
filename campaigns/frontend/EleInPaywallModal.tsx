import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Zap, 
  Check, 
  ArrowRight, 
  ShieldCheck, 
  Calendar, 
  Bell, 
  X, 
  Rocket, 
  Sparkles, 
  Loader2 
} from 'lucide-react';
import { useEleInCheckout } from '@/hooks/useEleInCheckout';
import { useSWRConfig } from 'swr';
import { ElesiumLogo } from '@/components/ElesiumLogo';

interface EleInPaywallModalProps {
  isOpen: boolean;
  onClose: () => void;
  campaignName?: string;
  onSuccess?: () => void;
}

export const EleInPaywallModal: React.FC<EleInPaywallModalProps> = ({
  isOpen,
  onClose,
  campaignName = "Your Campaign",
  onSuccess,
}) => {
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [isAnnual, setIsAnnual] = useState(true);
  const [showExitIntent, setShowExitIntent] = useState(false);
  const { startCheckout, isProcessing, isVerifying, processingPackage } = useEleInCheckout();
  const { mutate } = useSWRConfig();

  if (!isOpen) return null;

  const handleCloseClick = () => {
    // Paranoia Layer 2: Prevent closing while payment verification is underway
    if (isVerifying) return;

    // Paranoia Layer 2: Catch accidental drop-off with exit-intent downsell
    if (!showExitIntent && step > 0) {
      setShowExitIntent(true);
    } else {
      setShowExitIntent(false);
      setStep(0);
      onClose();
    }
  };

  const handleUpgrade = (packageId: 'growth_tier' | 'growth_tier_annual') => {
    startCheckout({
      provider: 'razorpay',
      action: 'upgrade',
      packageId,
      onSuccess: () => {
        // Refresh workspace limits & campaign data across the app
        mutate('/api/elein/workspaces/billing');
        mutate('/api/elein/dashboard/stats');
        mutate('/api/elein/campaigns');
        if (onSuccess) {
          onSuccess();
        }
        onClose();
      },
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <motion.div 
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 10 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-xl rounded-3xl bg-card border border-primary/20 shadow-[0_0_50px_rgba(var(--primary),0.2)] p-6 md:p-8 text-foreground overflow-hidden"
      >
        {/* Ambient Top Glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-24 bg-primary/10 blur-3xl pointer-events-none" />

        {/* Close Button */}
        <button
          onClick={handleCloseClick}
          className="absolute top-6 right-6 text-muted-foreground hover:text-foreground p-1.5 rounded-full hover:bg-muted/50 transition z-10"
          aria-label="Close"
        >
          <X size={18} />
        </button>

        {/* EXIT INTENT SHEET (Downsell & Sunk Cost Protection) */}
        {showExitIntent ? (
          <div className="py-4 space-y-6 text-center animate-in fade-in duration-200">
            <div className="w-14 h-14 bg-amber-500/10 text-amber-400 rounded-2xl mx-auto flex items-center justify-center border border-amber-500/20">
              <Sparkles size={28} />
            </div>
            <div>
              <h3 className="text-2xl font-bold tracking-tight">Don't Lose Your Campaign Setup</h3>
              <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto leading-relaxed">
                Your sequence for <strong className="text-foreground">"{campaignName}"</strong> is fully configured and ready to generate replies.
              </p>
            </div>

            <div className="p-4 rounded-2xl bg-muted/30 border border-border/50 text-left space-y-2 text-xs">
              <div className="flex items-center gap-2 text-foreground font-medium">
                <Check size={14} className="text-primary" />
                <span>Not ready for Annual? Flexible Monthly plan available at ₹7,999/mo.</span>
              </div>
              <div className="flex items-center gap-2 text-foreground font-medium">
                <Check size={14} className="text-primary" />
                <span>Your nodes, AI prompt prompts, and lead enrollments remain 100% safe.</span>
              </div>
            </div>

            <div className="space-y-3 pt-2">
              <button
                disabled={isProcessing}
                onClick={() => handleUpgrade('growth_tier')}
                className="w-full py-3.5 px-4 rounded-xl bg-primary text-primary-foreground font-bold hover:bg-primary/90 transition shadow-lg flex items-center justify-center gap-2"
              >
                {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} className="fill-current" />}
                Switch to Flexible Monthly (₹7,999/mo) <ArrowRight size={16} />
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowExitIntent(false);
                  onClose();
                }}
                className="text-xs text-muted-foreground/70 hover:text-rose-500 transition pt-2 block mx-auto"
              >
                I'll risk pausing outreach on "{campaignName}" for now
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* STEP 0: Outcome & ROI Priming */}
            {step === 0 && (
              <div className="space-y-5 py-2">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-primary/10 text-primary rounded-xl border border-primary/20">
                    <Rocket size={22} />
                  </div>
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-primary">Target Ready</span>
                    <h2 className="text-xl font-bold tracking-tight">Launch "{campaignName}"</h2>
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-primary/5 border border-primary/20 space-y-2">
                  <div className="flex items-center justify-between text-xs font-semibold text-primary">
                    <span>Campaign Potential</span>
                    <span className="bg-primary/20 px-2 py-0.5 rounded-full">High Impact</span>
                  </div>
                  <p className="text-sm text-foreground leading-relaxed">
                    On <strong className="text-primary">Growth Tier</strong>, this campaign can run continuously with unlimited active contacts, generating an estimated <strong className="text-primary">35-50 qualified replies every week</strong>.
                  </p>
                </div>

                {/* Anchoring & Contrast Engine (Transcript 2, Principle 6) */}
                <div className="grid grid-cols-2 gap-2 text-left p-3 rounded-2xl bg-muted/30 border border-border/40 text-xs">
                  <div className="p-2.5 rounded-xl bg-background/50 border border-border/30">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
                      Full-time SDR Hire
                    </span>
                    <span className="text-sm font-bold text-foreground">₹75,000+ / mo</span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">300 manual contacts/mo</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-primary/10 border border-primary/30">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-primary block">
                      Ele-in Growth Engine
                    </span>
                    <span className="text-sm font-bold text-primary">₹6,499 / mo</span>
                    <span className="text-[10px] text-emerald-500 font-semibold block mt-0.5">&lt; 9% cost • 24/7 Autopilot</span>
                  </div>
                </div>

                <div className="space-y-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <Check size={14} className="text-primary shrink-0" />
                    <span>Free Tier is capped at 1 active campaign. Upgrade unlocks 20 active campaigns.</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Check size={14} className="text-primary shrink-0" />
                    <span className="flex items-center gap-1.5">
                      <ElesiumLogo size={12} />
                      <span>Includes 5,000 monthly credits for AI replies & Apollo enrichment.</span>
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => setStep(1)}
                  className="w-full py-3.5 px-4 rounded-xl bg-primary text-primary-foreground font-bold hover:bg-primary/90 transition shadow-lg flex items-center justify-center gap-2 mt-3"
                >
                  See Growth Tier Details <ArrowRight size={16} />
                </button>
              </div>
            )}

            {/* STEP 1: Feature Matrix & Proof */}
            {step === 1 && (
              <div className="space-y-5 py-2">
                <div className="text-center">
                  <h2 className="text-xl font-bold">Free vs. Growth Tier</h2>
                  <p className="text-xs text-muted-foreground mt-1">Scale your outbound engine without arbitrary limits</p>
                </div>

                <div className="rounded-2xl border border-border bg-muted/20 overflow-hidden divide-y divide-border text-xs">
                  <div className="grid grid-cols-3 p-3 font-semibold bg-muted/40 text-muted-foreground">
                    <span>Feature</span>
                    <span className="text-center">Free Tier</span>
                    <span className="text-center text-primary font-bold">Growth Tier</span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">Active Campaigns</span>
                    <span className="text-center text-muted-foreground">1 Max</span>
                    <span className="text-center font-bold text-primary">20 Active</span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">Monthly Credits</span>
                    <span className="text-center text-muted-foreground">500</span>
                    <span className="text-center font-bold text-primary">5,000 / mo</span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">Apollo & Webhooks</span>
                    <span className="text-center text-muted-foreground">Disabled</span>
                    <span className="text-center font-bold text-emerald-400">Full Access</span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">Sending Accounts</span>
                    <span className="text-center text-muted-foreground">1 LinkedIn</span>
                    <span className="text-center font-bold text-primary">Up to 5 Accounts</span>
                  </div>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={() => setStep(0)}
                    className="px-4 py-3 rounded-xl border border-border text-muted-foreground hover:text-foreground text-xs font-semibold transition"
                  >
                    Back
                  </button>
                  <button
                    onClick={() => setStep(2)}
                    className="flex-1 py-3 px-4 rounded-xl bg-primary text-primary-foreground font-bold hover:bg-primary/90 transition shadow-lg flex items-center justify-center gap-2 text-sm"
                  >
                    Select Plan & Launch <ArrowRight size={16} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 2: Blinkist-Style Risk Reversal Timeline & Plan Selector */}
            {step === 2 && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-xl font-bold tracking-tight">Upgrade to Growth Tier</h2>
                  <p className="text-xs text-muted-foreground mt-1">Activate instantly and launch your campaigns right now.</p>
                </div>

                {/* Risk Reversal Timeline */}
                <div className="bg-muted/30 border border-border/60 rounded-2xl p-4 space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-primary/20 text-primary rounded-xl shrink-0 mt-0.5">
                      <Zap size={14} />
                    </div>
                    <div className="text-xs">
                      <div className="font-semibold text-foreground">Immediate Activation</div>
                      <div className="text-muted-foreground text-[11px]">Your campaign "{campaignName}" is instantly launched with unlimited capacity.</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-emerald-500/20 text-emerald-400 rounded-xl shrink-0 mt-0.5">
                      <ShieldCheck size={14} />
                    </div>
                    <div className="text-xs">
                      <div className="font-semibold text-foreground flex items-center gap-1.5">
                        <ElesiumLogo size={12} />
                        <span>Overdraft Protection Included</span>
                      </div>
                      <div className="text-muted-foreground text-[11px]">Never miss a warm lead: covers up to -500 credits for inflight AI replies.</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-amber-500/20 text-amber-400 rounded-xl shrink-0 mt-0.5">
                      <Calendar size={14} />
                    </div>
                    <div className="text-xs">
                      <div className="font-semibold text-foreground">Zero Lock-in</div>
                      <div className="text-muted-foreground text-[11px]">Change plans or cancel renewal anytime from Billing settings.</div>
                    </div>
                  </div>
                </div>

                {/* Annual vs Monthly Toggle */}
                <div className="grid grid-cols-2 gap-3">
                  <div
                    onClick={() => setIsAnnual(true)}
                    className={`p-4 rounded-2xl border cursor-pointer transition relative ${
                      isAnnual
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border bg-card hover:border-foreground/20'
                    }`}
                  >
                    <span className="absolute -top-2.5 right-3 text-[9px] bg-primary text-primary-foreground font-black px-2 py-0.5 rounded-full uppercase tracking-wider shadow">
                      Save 2 Months
                    </span>
                    <div className="font-bold text-sm text-foreground">Annual Plan</div>
                    <div className="text-xs text-primary font-bold mt-1">₹6,499 <span className="text-muted-foreground font-normal">/ mo</span></div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">₹77,988 billed yearly</div>
                  </div>

                  <div
                    onClick={() => setIsAnnual(false)}
                    className={`p-4 rounded-2xl border cursor-pointer transition ${
                      !isAnnual
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border bg-card hover:border-foreground/20'
                    }`}
                  >
                    <div className="font-bold text-sm text-foreground">Monthly Plan</div>
                    <div className="text-xs text-foreground font-bold mt-1">₹7,999 <span className="text-muted-foreground font-normal">/ mo</span></div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">Billed monthly</div>
                  </div>
                </div>

                {/* CTA with Right Chevron & Trust Subtitle */}
                <div className="space-y-2.5 text-center pt-1">
                  <button
                    disabled={isProcessing || isVerifying}
                    onClick={() => handleUpgrade(isAnnual ? 'growth_tier_annual' : 'growth_tier')}
                    className="w-full py-4 px-4 rounded-xl bg-primary text-primary-foreground font-bold hover:bg-primary/90 disabled:opacity-50 transition shadow-xl flex items-center justify-center gap-2 group"
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 size={18} className="animate-spin" />
                        <span>Initializing Secure Gateway...</span>
                      </>
                    ) : isVerifying ? (
                      <>
                        <Loader2 size={18} className="animate-spin text-amber-300" />
                        <span>Confirming Payment & Upgrading...</span>
                      </>
                    ) : (
                      <>
                        <Zap size={18} className="fill-current" />
                        <span>Upgrade & Launch Campaign</span>
                        <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                      </>
                    )}
                  </button>
                  <p className="text-[11px] text-muted-foreground flex items-center justify-center gap-1.5">
                    <ShieldCheck size={12} className="text-primary" />
                    <span>Secure encrypted checkout via Razorpay • Cancel anytime</span>
                  </p>
                </div>
              </div>
            )}
          </>
        )}
      </motion.div>
    </div>
  );
};
