import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Trophy, 
  Sparkles, 
  Clock, 
  CheckCircle2, 
  ArrowRight, 
  X, 
  Loader2, 
  ShieldCheck, 
  Lock, 
  Zap, 
  Flame 
} from 'lucide-react';
import { useEleInCheckout } from '@/hooks/useEleInCheckout';
import useSWR, { useSWRConfig } from 'swr';
import { fetcher } from '@/lib/apiClient';
import { toast } from 'sonner';
import { ElesiumLogo } from '@/components/ElesiumLogo';

interface FirstWinMilestoneModalProps {
  isOpen: boolean;
  onClose: () => void;
  prospectName?: string;
  campaignName?: string;
  onSuccess?: () => void;
}

export const FirstWinMilestoneModal: React.FC<FirstWinMilestoneModalProps> = ({
  isOpen,
  onClose,
  prospectName = 'Your prospect',
  campaignName = 'Outreach Campaign',
  onSuccess,
}) => {
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('annual');
  const [timeLeft, setTimeLeft] = useState<{ hours: number; minutes: number; seconds: number }>({
    hours: 47,
    minutes: 59,
    seconds: 59,
  });

  const { startCheckout, isProcessing, isVerifying } = useEleInCheckout();
  const { mutate } = useSWRConfig();

  const workspaceId = typeof window !== 'undefined' ? (localStorage.getItem('elein_active_workspace') || 'default') : 'default';

  // Paranoia Layer 1 & 2: Server-authoritative 48-hour OTO promotional metadata
  const { data: billingData } = useSWR<{
    tier?: string;
    first_win_at?: string | null;
    oto_expires_at?: string | null;
    oto_expired?: boolean;
  }>('/api/elein/workspaces/billing', fetcher);

  // Paranoia Layer 1: Persistent 48-hour OTO expiry timestamp anchored to server telemetry
  useEffect(() => {
    if (!isOpen) return;

    const storageKey = `elein_oto_expires_at_${workspaceId}`;
    let targetTimestamp: number;

    if (billingData?.oto_expires_at) {
      targetTimestamp = new Date(billingData.oto_expires_at).getTime();
      try {
        localStorage.setItem(storageKey, String(targetTimestamp));
      } catch (_) {}
    } else if (billingData?.oto_expired) {
      targetTimestamp = 0;
    } else {
      let expiry = localStorage.getItem(storageKey);
      if (!expiry) {
        const targetTime = Date.now() + 48 * 60 * 60 * 1000; // 48 hours fallback
        localStorage.setItem(storageKey, String(targetTime));
        expiry = String(targetTime);
      }
      targetTimestamp = parseInt(expiry, 10);
    }

    const updateTimer = () => {
      const now = Date.now();
      const diff = Math.max(0, targetTimestamp - now);

      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      setTimeLeft({ hours, minutes, seconds });
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [isOpen, workspaceId, billingData]);

  const isExpired = Boolean(billingData?.oto_expired) || (timeLeft.hours === 0 && timeLeft.minutes === 0 && timeLeft.seconds === 0);

  if (!isOpen) return null;

  const handleDismiss = () => {
    if (isProcessing || isVerifying) return;
    try {
      localStorage.setItem(`elein_milestone_dismissed_${workspaceId}`, 'true');
    } catch (_) {}
    onClose();
  };

  const handleClaimOffer = () => {
    // Paranoia Layer 2: Reject client-side action if promotional timer has elapsed
    if (isExpired) {
      toast.error('The 48-hour First-Win momentum grant has expired for this account.');
      return;
    }

    const packageId = billingCycle === 'annual' ? 'growth_tier_annual_oto' : 'growth_tier_oto';
    
    startCheckout({
      provider: 'razorpay',
      action: 'upgrade',
      packageId,
      onSuccess: () => {
        toast.success("Upgrade complete! Growth Tier unlocked with grandfathered discount.");
        mutate('/api/elein/workspaces/billing');
        mutate('/api/elein/billing/credits/balance');
        mutate('/api/elein/dashboard/stats');
        try {
          localStorage.setItem(`elein_milestone_claimed_${workspaceId}`, 'true');
        } catch (_) {}
        if (onSuccess) onSuccess();
        onClose();
      },
    });
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-4 overflow-y-auto">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="relative w-full max-w-2xl rounded-xl bg-card border border-border/80 shadow-2xl p-6 md:p-8 text-foreground overflow-hidden my-8"
        >
          {/* Dismiss button */}
          <button
            type="button"
            disabled={isProcessing || isVerifying}
            onClick={handleDismiss}
            className="absolute top-5 right-5 text-muted-foreground hover:text-foreground p-1.5 rounded-full hover:bg-muted/50 transition z-10 disabled:opacity-40"
            aria-label="Close"
          >
            <X size={18} />
          </button>

          {/* Milestone Badge & Header */}
          <div className="flex flex-col items-center text-center mb-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs font-semibold mb-3">
              <Trophy size={14} className="text-amber-600 dark:text-amber-400" />
              <span>FIRST-WIN MILESTONE ACHIEVED</span>
            </div>

            <h2 className="text-2xl md:text-3xl font-extrabold tracking-tight text-foreground mb-2">
              Your Campaign Just Booked Its First Reply!
            </h2>
            <p className="text-sm text-muted-foreground max-w-lg leading-relaxed">
              <span className="text-foreground font-medium">{prospectName}</span> responded to{' '}
              <span className="text-foreground font-medium">{campaignName}</span>. You've officially proven that your messaging resonates with high-value prospects.
            </p>
          </div>

          {/* 48-Hour OTO Banner with Live Countdown */}
          <div className="rounded-lg bg-muted/30 border border-border/60 p-4 mb-6 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-600 dark:text-amber-400 shrink-0">
                <Flame size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider">
                    48-Hour Momentum Grant
                  </span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                    30% OFF
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Exclusive expansion discount for users who achieve their first prospect reply.
                </p>
              </div>
            </div>

            {/* Live Countdown Clock */}
            <div className="flex items-center gap-1.5 bg-background border border-border/60 px-3 py-1.5 rounded-md shrink-0">
              <Clock size={14} className="text-amber-600 dark:text-amber-400" />
              <span className="font-mono text-xs font-bold text-foreground">
                {isExpired ? (
                  'OFFER EXPIRED'
                ) : (
                  `${String(timeLeft.hours).padStart(2, '0')}h ${String(timeLeft.minutes).padStart(2, '0')}m ${String(timeLeft.seconds).padStart(2, '0')}s`
                )}
              </span>
            </div>
          </div>

          {/* Free vs Growth Scale Comparison */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
            {/* Free Limits */}
            <div className="p-4 rounded-lg bg-muted/30 border border-border/60 flex flex-col justify-between">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">
                  Current Free Tier
                </span>
                <span className="text-lg font-bold text-foreground">1 Campaign Limit</span>
                <ul className="mt-3 space-y-2 text-xs text-muted-foreground">
                  <li className="flex items-center gap-2">
                    <span className="text-muted-foreground/60">•</span> 500 total monthly credits
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-muted-foreground/60">•</span> ~25 prospects enriched/mo
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-muted-foreground/60">•</span> 1 LinkedIn account connected
                  </li>
                </ul>
              </div>
              <div className="mt-4 pt-3 border-t border-border/60 text-[11px] text-muted-foreground italic">
                Cap reached quickly once multiple leads reply.
              </div>
            </div>

            {/* Growth Tier Unlocked */}
            <div className="p-4 rounded-lg bg-card border border-border/60 flex flex-col justify-between relative overflow-hidden">
              <div className="absolute top-2 right-2">
                <span className="text-[9px] font-bold px-2 py-0.5 rounded-md bg-primary/10 text-primary border border-primary/20 uppercase tracking-wider">
                  Recommended
                </span>
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-primary block mb-1">
                  Growth Pro Scale
                </span>
                <span className="text-lg font-bold text-foreground flex items-center gap-2">
                  <span>20 Active Campaigns</span>
                  <Zap size={16} className="text-primary fill-primary" />
                </span>
                <ul className="mt-3 space-y-2 text-xs text-muted-foreground">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                    <span><strong className="text-foreground">5,000 credits/mo</strong> (60,000/yr)</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                    <span className="flex items-center gap-1.5">
                      <ElesiumLogo size={12} />
                      <span><strong className="text-foreground">Unlimited AI Ghostwriter</strong> streaming</span>
                    </span>
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                    <span><strong className="text-foreground">Up to 5 accounts</strong> & multi-inbox</span>
                  </li>
                </ul>
              </div>
              <div className="mt-4 pt-3 border-t border-border/60 text-[11px] text-primary font-medium">
                Proven ~35–50 booked meetings/month potential
              </div>
            </div>
          </div>

          {/* Pricing Cycle Selector */}
          <div className="flex items-center justify-center gap-3 mb-6">
            <button
              type="button"
              onClick={() => setBillingCycle('monthly')}
              className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all border ${
                billingCycle === 'monthly'
                  ? 'bg-muted text-foreground border-border shadow-sm'
                  : 'text-muted-foreground hover:text-foreground border-transparent'
              }`}
            >
              Monthly: <span className="text-emerald-600 dark:text-emerald-400 font-bold">$69/mo</span>{' '}
              <span className="line-through text-muted-foreground text-[11px]">$99</span>
            </button>
            <button
              type="button"
              onClick={() => setBillingCycle('annual')}
              className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all border relative ${
                billingCycle === 'annual'
                  ? 'bg-primary/10 text-foreground border-primary/30 shadow-sm'
                  : 'text-muted-foreground hover:text-foreground border-transparent'
              }`}
            >
              Annual:{' '}
              <span className="text-emerald-600 dark:text-emerald-400 font-bold">$55/mo</span>{' '}
              <span className="line-through text-muted-foreground text-[11px]">$79</span>
              <span className="ml-1.5 px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold border border-emerald-500/20">
                SAVE 44%
              </span>
            </button>
          </div>

          {/* Price Guarantee Badge */}
          <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground mb-6">
            <Lock size={12} className="text-amber-500 dark:text-amber-400" />
            <span>Grandfathered Rate: This 30% discount stays locked for the life of your account.</span>
          </div>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row items-center gap-3">
            <button
              type="button"
              disabled={isProcessing || isVerifying || isExpired}
              onClick={handleClaimOffer}
              className="w-full sm:flex-1 py-3 px-6 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-sm transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isProcessing || isVerifying ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>{isVerifying ? 'Verifying & Synchronizing...' : 'Opening Checkout...'}</span>
                </>
              ) : isExpired ? (
                <>
                  <Lock size={16} className="text-primary-foreground/60" />
                  <span>Offer Expired</span>
                </>
              ) : (
                <>
                  <span>Claim 30% Off & Scale Pipeline</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>

            <button
              type="button"
              disabled={isProcessing || isVerifying}
              onClick={handleDismiss}
              className="w-full sm:w-auto py-3 px-5 rounded-lg bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground text-xs font-semibold transition-all border border-border/60"
            >
              Keep Free Plan for Now
            </button>
          </div>

          {/* Reassurance */}
          <div className="mt-4 flex items-center justify-center gap-4 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <ShieldCheck size={13} className="text-emerald-500 dark:text-emerald-400" /> 14-day money-back guarantee
            </span>
            <span>•</span>
            <span>1-click instant cancellation</span>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
