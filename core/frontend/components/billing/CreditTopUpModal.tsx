import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Coins, Zap, ShieldCheck, ArrowRight, X, Loader2, Sparkles, ExternalLink } from 'lucide-react';
import { useEleInCheckout } from '@/hooks/useEleInCheckout';
import useSWR, { useSWRConfig } from 'swr';
import { fetcher } from '@/lib/apiClient';
import { useNavigate } from 'react-router-dom';

interface CreditTopUpModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentBalance?: number;
  onSuccess?: () => void;
}

export const CreditTopUpModal: React.FC<CreditTopUpModalProps> = ({
  isOpen,
  onClose,
  currentBalance,
  onSuccess,
}) => {
  const [selectedOption, setSelectedOption] = useState<'credits' | 'growth'>('credits');
  const { startCheckout, isProcessing, isVerifying } = useEleInCheckout();
  const { mutate } = useSWRConfig();
  const navigate = useNavigate();

  // Paranoia Layer 0 & 1: Fetch live balance from canonical endpoint if prop not supplied
  const { data: balanceData } = useSWR(
    isOpen ? '/api/elein/billing/credits/balance' : null,
    fetcher
  );

  const displayBalance =
    currentBalance !== undefined
      ? currentBalance
      : Number(balanceData?.balance ?? balanceData?.data_cleaning_credits ?? 0);

  if (!isOpen) return null;

  const handlePurchase = () => {
    if (selectedOption === 'credits') {
      startCheckout({
        provider: 'razorpay',
        action: 'credits',
        packageId: 'credits_1000',
        onSuccess: () => {
          mutate('/api/elein/billing/credits/balance');
          mutate('/api/elein/workspaces/billing');
          mutate('/api/elein/dashboard/stats');
          if (onSuccess) onSuccess();
          onClose();
        },
      });
    } else {
      startCheckout({
        provider: 'razorpay',
        action: 'upgrade',
        packageId: 'growth_tier',
        onSuccess: () => {
          mutate('/api/elein/billing/credits/balance');
          mutate('/api/elein/workspaces/billing');
          mutate('/api/elein/dashboard/stats');
          if (onSuccess) onSuccess();
          onClose();
        },
      });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 10 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-lg rounded-xl bg-card border border-border/80 shadow-2xl p-6 md:p-8 text-foreground overflow-hidden"
      >
        {/* Close Button */}
        <button
          type="button"
          disabled={isProcessing || isVerifying}
          onClick={onClose}
          className="absolute top-6 right-6 text-muted-foreground hover:text-foreground p-1.5 rounded-full hover:bg-muted/50 transition z-10 disabled:opacity-40"
          aria-label="Close"
        >
          <X size={18} />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3.5 mb-6">
          <div className="p-3 bg-primary/10 text-primary rounded-lg border border-primary/20">
            <Coins size={24} />
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-primary">Micro Top-Up</span>
            <h2 className="text-xl font-bold tracking-tight text-foreground">Workspace Platform Credits</h2>
          </div>
        </div>

        {/* Current Balance Bar */}
        <div className="p-4 rounded-lg bg-muted/30 border border-border/60 flex items-center justify-between mb-6 text-xs">
          <div>
            <span className="text-muted-foreground block text-[11px]">Current Balance</span>
            <span className="text-foreground font-mono font-bold text-base mt-0.5 block">
              {displayBalance.toLocaleString()} Credits
            </span>
          </div>
          <div className="text-right">
            <span className="text-muted-foreground block text-[11px]">Overdraft Buffer</span>
            <span className="text-emerald-400 font-semibold text-xs mt-0.5 block">
              Covered to -500 credits
            </span>
          </div>
        </div>

        {/* Options */}
        <div className="space-y-3 mb-6">
          {/* Option A: Buy 1,000 Credits */}
          <button
            type="button"
            onClick={() => setSelectedOption('credits')}
            aria-pressed={selectedOption === 'credits'}
            className={`w-full text-left p-4 rounded-lg border transition relative focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
              selectedOption === 'credits'
                ? 'border-primary bg-primary/5 ring-1 ring-primary'
                : 'border-border bg-card hover:border-foreground/20'
            }`}
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-bold text-sm text-foreground flex items-center gap-2">
                  <Coins size={15} className="text-primary" />
                  <span>1,000 Instant Credits</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Covers ~200 AI reply drafts or 200 Apollo contact enrichments.
                </p>
              </div>
              <div className="text-right">
                <span className="font-bold text-base text-foreground">₹999</span>
                <span className="block text-[10px] text-muted-foreground">one-time</span>
              </div>
            </div>
          </button>

          {/* Option B: Upgrade to Growth Tier */}
          <button
            type="button"
            onClick={() => setSelectedOption('growth')}
            aria-pressed={selectedOption === 'growth'}
            className={`w-full text-left p-4 rounded-lg border transition relative focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
              selectedOption === 'growth'
                ? 'border-primary bg-primary/5 ring-1 ring-primary'
                : 'border-border bg-card hover:border-foreground/20'
            }`}
          >
            <span className="absolute -top-2.5 right-4 text-[9px] bg-primary text-primary-foreground font-bold px-2 py-0.5 rounded-md uppercase tracking-wider shadow-sm z-10">
              Best Value
            </span>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-bold text-sm text-foreground flex items-center gap-2">
                  <Sparkles size={15} className="text-primary" />
                  <span>Growth Tier Upgrade</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  5,000 credits/mo + 20 active campaigns + 5 sender accounts.
                </p>
              </div>
              <div className="text-right">
                <span className="font-bold text-base text-primary">₹7,999</span>
                <span className="block text-[10px] text-muted-foreground">/ month</span>
              </div>
            </div>
          </button>
        </div>

        {/* Action Button */}
        <div className="space-y-3">
          <button
            type="button"
            disabled={isProcessing || isVerifying}
            onClick={handlePurchase}
            className="w-full py-3.5 px-4 rounded-lg bg-primary text-primary-foreground font-bold hover:bg-primary/90 disabled:opacity-50 transition shadow-lg flex items-center justify-center gap-2 group text-sm"
          >
            {isProcessing ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                <span>Opening Gateway...</span>
              </>
            ) : isVerifying ? (
              <>
                <Loader2 size={18} className="animate-spin text-amber-300" />
                <span>Confirming Credit Top-Up...</span>
              </>
            ) : (
              <>
                <Zap size={16} className="fill-current" />
                <span>
                  {selectedOption === 'credits' ? 'Purchase 1,000 Credits (₹999)' : 'Upgrade to Growth Tier (₹7,999)'}
                </span>
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </>
            )}
          </button>

          <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <ShieldCheck size={12} className="text-primary" /> Encrypted Razorpay Checkout
            </span>
            <button
              type="button"
              onClick={() => {
                onClose();
                navigate('/elein/billing');
              }}
              className="hover:text-foreground transition underline flex items-center gap-1"
            >
              Detailed Billing <ExternalLink size={10} />
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
