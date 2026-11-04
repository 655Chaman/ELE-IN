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
import useSWR, { useSWRConfig } from 'swr';
import { fetcher } from '@/lib/apiClient';
import { ElesiumLogo } from '@/components/ElesiumLogo';

interface EleInPaywallModalProps {
  isOpen: boolean;
  onClose: () => void;
  campaignName?: string;
  featureName?: string;
  minTier?: string;
  onSuccess?: () => void;
}

export const EleInPaywallModal: React.FC<EleInPaywallModalProps> = ({
  isOpen,
  onClose,
  campaignName = "Your Campaign",
  featureName,
  minTier,
  onSuccess,
}) => {
  const { data: billingData } = useSWR<{ tier?: string; is_platform_owner?: boolean }>('/api/elein/workspaces/billing', fetcher);
  const isOwner = Boolean(billingData?.is_platform_owner);

  // Owner auto-bypass: If mounted directly, complete without rendering paywall
  React.useEffect(() => {
    if (isOpen && isOwner) {
      if (onSuccess) onSuccess();
      onClose();
    }
  }, [isOpen, isOwner, onSuccess, onClose]);

  if (isOpen && isOwner) return null;

  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [isAnnual, setIsAnnual] = useState(true);
  const [selectedTier, setSelectedTier] = useState<'growth' | 'enterprise'>(
    minTier?.toUpperCase() === 'ENTERPRISE' ? 'enterprise' : 'growth'
  );
  const [showExitIntent, setShowExitIntent] = useState(false);
  const { startCheckout, isProcessing, isVerifying, processingPackage } = useEleInCheckout();
  const { mutate } = useSWRConfig();

  React.useEffect(() => {
    if (minTier?.toUpperCase() === 'ENTERPRISE') {
      setSelectedTier('enterprise');
    }
  }, [minTier]);

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

  // Paranoia Layer 1 & 2 (FLAW-FE-16): Handle Escape key dismissal gracefully
  React.useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleCloseClick();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isVerifying, showExitIntent, step]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    // Dismiss only when the click is on the backdrop itself, not inside the modal container
    if (e.target === e.currentTarget) {
      handleCloseClick();
    }
  };

  const handleUpgrade = (packageId: string) => {
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
    <div 
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 cursor-default"
      role="dialog"
      aria-modal="true"
      aria-labelledby="paywall-title"
    >
      <motion.div 
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 10 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-xl rounded-xl bg-card border border-border/80 shadow-2xl p-6 md:p-8 text-foreground overflow-hidden"
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={handleCloseClick}
          className="absolute top-6 right-6 text-muted-foreground hover:text-foreground p-1.5 rounded-full hover:bg-muted/50 transition z-10 cursor-pointer"
          aria-label="Close"
        >
          <X size={18} />
        </button>

        {/* EXIT INTENT SHEET (Downsell & Sunk Cost Protection) */}
        {showExitIntent ? (
          <div className="py-4 space-y-6 text-center animate-in fade-in duration-200">
            <div className="w-14 h-14 bg-amber-500/10 text-amber-400 rounded-md mx-auto flex items-center justify-center border border-amber-500/20">
              <Sparkles size={28} />
            </div>
            <div>
              <h3 className="text-2xl font-bold tracking-tight">Don't Lose Your Campaign Setup</h3>
              <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto leading-relaxed">
                Your sequence for <strong className="text-foreground">"{campaignName}"</strong> is fully configured and ready to generate replies.
              </p>
            </div>

            <div className="p-4 rounded-lg bg-muted/30 border border-border/50 text-left space-y-2 text-xs">
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
                type="button"
                disabled={isProcessing}
                onClick={() => handleUpgrade('growth_tier')}
                className="w-full py-3.5 px-4 rounded-lg bg-primary text-primary-foreground font-bold hover:bg-primary/90 transition shadow-sm flex items-center justify-center gap-2 cursor-pointer"
              >
                {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} className="fill-current" />}
                Switch to Flexible Monthly (₹7,999/mo) <ArrowRight size={16} />
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowExitIntent(false);
                  setStep(0);
                  onClose();
                }}
                className="text-xs text-muted-foreground/70 hover:text-rose-500 transition pt-2 block mx-auto cursor-pointer"
              >
                I'll risk pausing outreach on "{campaignName}" for now
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Tier Switcher Pill Navigation */}
            <div className="flex items-center justify-center gap-2 mb-4">
              <button
                type="button"
                onClick={() => setSelectedTier('growth')}
                className={`px-3 py-1 rounded-full text-xs font-bold transition-all border cursor-pointer ${
                  selectedTier === 'growth'
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40 shadow-xs'
                    : 'bg-muted/40 text-muted-foreground border-border hover:text-foreground'
                }`}
              >
                Growth Pro
              </button>
              <button
                type="button"
                onClick={() => setSelectedTier('enterprise')}
                className={`px-3 py-1 rounded-full text-xs font-bold transition-all border cursor-pointer ${
                  selectedTier === 'enterprise'
                    ? 'bg-purple-500/15 text-purple-400 border-purple-500/40 shadow-xs'
                    : 'bg-muted/40 text-muted-foreground border-border hover:text-foreground'
                }`}
              >
                Enterprise VIP
              </button>
            </div>

            {/* STEP 0: Outcome & ROI Priming */}
            {step === 0 && (
              <div className="space-y-5 py-2">
                <div className="flex items-center gap-3">
                  <div className={`p-2.5 rounded-md border ${
                    selectedTier === 'enterprise'
                      ? 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                      : 'bg-primary/10 text-primary border-primary/20'
                  }`}>
                    <Rocket size={22} />
                  </div>
                  <div>
                    <span className={`text-[11px] font-bold uppercase tracking-wider ${
                      selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'
                    }`}>
                      {selectedTier === 'enterprise' ? 'Enterprise Infrastructure' : 'Target Ready'}
                    </span>
                    <h2 className="text-xl font-bold tracking-tight">Launch "{campaignName}"</h2>
                  </div>
                </div>

                <div className={`p-4 rounded-lg border space-y-2 ${
                  selectedTier === 'enterprise'
                    ? 'bg-purple-500/5 border-purple-500/30'
                    : 'bg-primary/5 border-primary/20'
                }`}>
                  <div className="flex items-center justify-between text-xs font-semibold">
                    <span className={selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'}>
                      {selectedTier === 'enterprise' ? 'Enterprise Stealth Moat' : 'Campaign Potential'}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      selectedTier === 'enterprise' ? 'bg-purple-500/20 text-purple-300' : 'bg-primary/20 text-primary'
                    }`}>
                      {selectedTier === 'enterprise' ? 'Zero-Ban Security' : 'High Impact'}
                    </span>
                  </div>
                  <p className="text-sm text-foreground leading-relaxed">
                    {selectedTier === 'enterprise' ? (
                      <>
                        Unlock <strong className="text-purple-400">Enterprise VIP Infrastructure</strong>: Multi-account Sender Pods, Ghidra Wasm Canary Fingerprint Shield, Residential IP rotation, and <strong className="text-purple-400">25,000 monthly credits</strong>.
                      </>
                    ) : (
                      <>
                        On <strong className="text-primary">Growth Tier</strong>, this campaign can run continuously with unlimited active contacts, generating an estimated <strong className="text-primary">35-50 qualified replies every week</strong>.
                      </>
                    )}
                  </p>
                </div>

                {/* Anchoring & Contrast Engine */}
                <div className="grid grid-cols-2 gap-2 text-left p-3 rounded-lg bg-muted/30 border border-border/40 text-xs">
                  <div className="p-2.5 rounded-md bg-background/50 border border-border/30">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
                      {selectedTier === 'enterprise' ? 'Agency Outbound Retainer' : 'Full-time SDR Hire'}
                    </span>
                    <span className="text-sm font-bold text-foreground">
                      {selectedTier === 'enterprise' ? '₹2,50,000+ / mo' : '₹75,000+ / mo'}
                    </span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      {selectedTier === 'enterprise' ? 'Manual, unmonitored sending' : '300 manual contacts/mo'}
                    </span>
                  </div>
                  <div className={`p-2.5 rounded-md border ${
                    selectedTier === 'enterprise'
                      ? 'bg-purple-500/10 border-purple-500/30 text-purple-400'
                      : 'bg-primary/10 border-primary/30 text-primary'
                  }`}>
                    <span className="text-[10px] uppercase font-bold tracking-wider block">
                      {selectedTier === 'enterprise' ? 'Ele-In Enterprise Suite' : 'Ele-in Growth Engine'}
                    </span>
                    <span className="text-sm font-bold">
                      {selectedTier === 'enterprise' ? '₹15,999 / mo' : '₹6,499 / mo'}
                    </span>
                    <span className="text-[10px] text-emerald-500 font-semibold block mt-0.5">
                      {selectedTier === 'enterprise' ? 'Dedicated Pods • Ghidra Shield' : '< 9% cost • 24/7 Autopilot'}
                    </span>
                  </div>
                </div>

                <div className="space-y-2 text-xs text-muted-foreground">
                  {selectedTier === 'enterprise' ? (
                    <>
                      <div className="flex items-center gap-2">
                        <Check size={14} className="text-purple-400 shrink-0" />
                        <span>Dedicated Sender Pods with automatic residential IP failover.</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Check size={14} className="text-purple-400 shrink-0" />
                        <span>Ghidra Wasm Canary Fingerprint Shield & SOC2 Type II Audit Log.</span>
                      </div>
                    </>
                  ) : (
                    <>
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
                    </>
                  )}
                </div>

                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className={`w-full py-3.5 px-4 rounded-lg font-bold transition shadow-sm flex items-center justify-center gap-2 mt-3 cursor-pointer ${
                    selectedTier === 'enterprise'
                      ? 'bg-purple-600 text-white hover:bg-purple-700'
                      : 'bg-primary text-primary-foreground hover:bg-primary/90'
                  }`}
                >
                  See {selectedTier === 'enterprise' ? 'Enterprise VIP' : 'Growth Tier'} Details <ArrowRight size={16} />
                </button>
              </div>
            )}

            {/* STEP 1: Feature Matrix & Proof */}
            {step === 1 && (
              <div className="space-y-5 py-2">
                <div className="text-center">
                  <h2 className="text-xl font-bold">
                    {selectedTier === 'enterprise' ? 'Growth Pro vs. Enterprise VIP' : 'Free vs. Growth Tier'}
                  </h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    {selectedTier === 'enterprise'
                      ? 'Enterprise infrastructure designed for agency scaling and zero account bans'
                      : 'Scale your outbound engine without arbitrary limits'}
                  </p>
                </div>

                <div className="rounded-lg border border-border bg-muted/20 overflow-hidden divide-y divide-border text-xs">
                  <div className="grid grid-cols-3 p-3 font-semibold bg-muted/40 text-muted-foreground">
                    <span>Feature</span>
                    <span className="text-center">{selectedTier === 'enterprise' ? 'Growth Pro' : 'Free Tier'}</span>
                    <span className={`text-center font-bold ${selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'}`}>
                      {selectedTier === 'enterprise' ? 'Enterprise VIP' : 'Growth Tier'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">Active Campaigns</span>
                    <span className="text-center text-muted-foreground">{selectedTier === 'enterprise' ? '20 Active' : '1 Max'}</span>
                    <span className={`text-center font-bold ${selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'}`}>
                      {selectedTier === 'enterprise' ? '50-100 Active' : '20 Active'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">Monthly Credits</span>
                    <span className="text-center text-muted-foreground">{selectedTier === 'enterprise' ? '5,000 / mo' : '500'}</span>
                    <span className={`text-center font-bold ${selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'}`}>
                      {selectedTier === 'enterprise' ? '25,000 / mo' : '5,000 / mo'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">
                      {selectedTier === 'enterprise' ? 'Stealth Warmup & Canary' : 'Apollo & Webhooks'}
                    </span>
                    <span className="text-center text-muted-foreground">
                      {selectedTier === 'enterprise' ? 'Standard Warmup' : 'Disabled'}
                    </span>
                    <span className="text-center font-bold text-emerald-400">
                      {selectedTier === 'enterprise' ? 'Ghidra Wasm Canary' : 'Full Access'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 p-3 items-center">
                    <span className="font-medium text-foreground">Sending Accounts</span>
                    <span className="text-center text-muted-foreground">{selectedTier === 'enterprise' ? 'Up to 5' : '1 LinkedIn'}</span>
                    <span className={`text-center font-bold ${selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'}`}>
                      {selectedTier === 'enterprise' ? '15-25 (Sender Pods)' : 'Up to 5 Accounts'}
                    </span>
                  </div>
                  {selectedTier === 'enterprise' && (
                    <div className="grid grid-cols-3 p-3 items-center">
                      <span className="font-medium text-foreground">Encryption & Audit</span>
                      <span className="text-center text-muted-foreground">Standard</span>
                      <span className="text-center font-bold text-purple-400">2-Tier Envelope & SOC2</span>
                    </div>
                  )}
                </div>

                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setStep(0)}
                    className="px-4 py-3 rounded-lg border border-border text-muted-foreground hover:text-foreground text-xs font-semibold transition cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={() => setStep(2)}
                    className={`flex-1 py-3 px-4 rounded-lg font-bold transition shadow-sm flex items-center justify-center gap-2 text-sm cursor-pointer ${
                      selectedTier === 'enterprise'
                        ? 'bg-purple-600 text-white hover:bg-purple-700'
                        : 'bg-primary text-primary-foreground hover:bg-primary/90'
                    }`}
                  >
                    Select Plan & Launch <ArrowRight size={16} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 2: Risk Reversal Timeline & Plan Selector */}
            {step === 2 && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-xl font-bold tracking-tight">
                    Upgrade to {selectedTier === 'enterprise' ? 'Enterprise VIP' : 'Growth Tier'}
                  </h2>
                  <p className="text-xs text-muted-foreground mt-1">Activate instantly and launch your campaigns right now.</p>
                </div>

                {/* Risk Reversal Timeline */}
                <div className="bg-muted/30 border border-border/60 rounded-lg p-4 space-y-3">
                  <div className="flex items-start gap-3">
                    <div className={`p-1.5 rounded-md shrink-0 mt-0.5 ${
                      selectedTier === 'enterprise' ? 'bg-purple-500/20 text-purple-400' : 'bg-primary/20 text-primary'
                    }`}>
                      <Zap size={14} />
                    </div>
                    <div className="text-xs">
                      <div className="font-semibold text-foreground">Immediate Activation</div>
                      <div className="text-muted-foreground text-[11px]">Your campaign "{campaignName}" is instantly launched with full capabilities.</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-emerald-500/20 text-emerald-400 rounded-md shrink-0 mt-0.5">
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
                    <div className="p-1.5 bg-amber-500/20 text-amber-400 rounded-md shrink-0 mt-0.5">
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
                  <button
                    type="button"
                    onClick={() => setIsAnnual(true)}
                    className={`w-full text-left p-4 rounded-lg border cursor-pointer transition relative ${
                      isAnnual
                        ? selectedTier === 'enterprise'
                          ? 'border-purple-500 bg-purple-500/5 ring-1 ring-purple-500'
                          : 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border bg-card hover:border-foreground/20'
                    }`}
                  >
                    <span className={`absolute -top-2.5 right-3 text-[9px] font-black px-2 py-0.5 rounded-full uppercase tracking-wider shadow-xs ${
                      selectedTier === 'enterprise' ? 'bg-purple-600 text-white' : 'bg-primary text-primary-foreground'
                    }`}>
                      Save 2 Months
                    </span>
                    <div className="font-bold text-sm text-foreground">Annual Plan</div>
                    <div className={`text-xs font-bold mt-1 ${selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'}`}>
                      {selectedTier === 'enterprise' ? '₹15,999' : '₹6,499'} <span className="text-muted-foreground font-normal">/ mo</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {selectedTier === 'enterprise' ? '₹1,91,988 billed yearly' : '₹77,988 billed yearly'}
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setIsAnnual(false)}
                    className={`w-full text-left p-4 rounded-lg border cursor-pointer transition ${
                      !isAnnual
                        ? selectedTier === 'enterprise'
                          ? 'border-purple-500 bg-purple-500/5 ring-1 ring-purple-500'
                          : 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border bg-card hover:border-foreground/20'
                    }`}
                  >
                    <div className="font-bold text-sm text-foreground">Monthly Plan</div>
                    <div className="text-xs text-foreground font-bold mt-1">
                      {selectedTier === 'enterprise' ? '₹19,999' : '₹7,999'} <span className="text-muted-foreground font-normal">/ mo</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">Billed monthly</div>
                  </button>
                </div>

                {/* CTA with Right Chevron & Trust Subtitle */}
                <div className="space-y-2.5 text-center pt-1">
                  <button
                    type="button"
                    disabled={isProcessing || isVerifying}
                    onClick={() => {
                      const targetPkg = selectedTier === 'enterprise'
                        ? (isAnnual ? 'agency_tier_annual' : 'agency_tier')
                        : (isAnnual ? 'growth_tier_annual' : 'growth_tier');
                      handleUpgrade(targetPkg);
                    }}
                    className={`w-full py-4 px-4 rounded-lg font-bold disabled:opacity-50 transition shadow-sm flex items-center justify-center gap-2 group cursor-pointer ${
                      selectedTier === 'enterprise'
                        ? 'bg-purple-600 text-white hover:bg-purple-700'
                        : 'bg-primary text-primary-foreground hover:bg-primary/90'
                    }`}
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
                        <span>Upgrade to {selectedTier === 'enterprise' ? 'Enterprise VIP' : 'Growth Pro'}</span>
                        <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                      </>
                    )}
                  </button>
                  <p className="text-[11px] text-muted-foreground flex items-center justify-center gap-1.5">
                    <ShieldCheck size={12} className={selectedTier === 'enterprise' ? 'text-purple-400' : 'text-primary'} />
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
