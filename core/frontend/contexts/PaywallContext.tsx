import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { fetcher } from '@/lib/apiClient';
import { EleInPaywallModal } from '@campaigns/EleInPaywallModal';
import { CreditTopUpModal } from '@/components/billing/CreditTopUpModal';
import { FirstWinMilestoneModal } from '@/components/billing/FirstWinMilestoneModal';

export interface PaywallTriggerOptions {
  campaignName?: string;
  featureName?: string;
  reason?: string;
  description?: string;
  minTier?: string;
  onSuccess?: () => void;
}

export interface TopUpTriggerOptions {
  neededCredits?: number;
  featureName?: string;
  onSuccess?: () => void;
}

export interface MilestoneTriggerOptions {
  milestoneType?: 'first_reply' | 'first_campaign' | 'first_win';
  prospectName?: string;
  campaignName?: string;
  onSuccess?: () => void;
}

interface PaywallContextType {
  openPaywall: (opts?: PaywallTriggerOptions | string) => void;
  closePaywall: () => void;
  openTopUp: (opts?: TopUpTriggerOptions) => void;
  closeTopUp: () => void;
  openMilestoneModal: (opts?: MilestoneTriggerOptions) => void;
  closeMilestoneModal: () => void;
  isPaywallOpen: boolean;
  isTopUpOpen: boolean;
  isMilestoneOpen: boolean;
}

const PaywallContext = createContext<PaywallContextType | undefined>(undefined);

export const PaywallProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isPaywallOpen, setIsPaywallOpen] = useState(false);
  const [paywallOptions, setPaywallOptions] = useState<PaywallTriggerOptions>({});

  const [isTopUpOpen, setIsTopUpOpen] = useState(false);
  const [topUpOptions, setTopUpOptions] = useState<TopUpTriggerOptions>({});

  const [isMilestoneOpen, setIsMilestoneOpen] = useState(false);
  const [milestoneOptions, setMilestoneOptions] = useState<MilestoneTriggerOptions>({});

  const { mutate } = useSWRConfig();
  const { data: balanceData } = useSWR('/api/elein/billing/credits/balance', fetcher);
  const currentCredits = Number(balanceData?.balance ?? balanceData?.data_cleaning_credits ?? 0);

  // Paranoia Layer 1: Concurrency Lock to prevent duplicate modal spam from parallel requests
  const isLockedRef = useRef(false);

  const openPaywall = useCallback((opts: PaywallTriggerOptions | string = {}) => {
    if (isPaywallOpen || isTopUpOpen || isMilestoneOpen || isLockedRef.current) return;
    isLockedRef.current = true;
    const normalizedOpts: PaywallTriggerOptions = typeof opts === 'string' ? { featureName: opts } : opts;
    setPaywallOptions(normalizedOpts);
    setIsPaywallOpen(true);
    setTimeout(() => {
      isLockedRef.current = false;
    }, 400);
  }, [isPaywallOpen, isTopUpOpen, isMilestoneOpen]);

  const closePaywall = useCallback(() => {
    setIsPaywallOpen(false);
    setPaywallOptions({});
  }, []);

  const openTopUp = useCallback((opts: TopUpTriggerOptions = {}) => {
    if (isTopUpOpen || isPaywallOpen || isMilestoneOpen || isLockedRef.current) return;
    isLockedRef.current = true;
    setTopUpOptions(opts);
    setIsTopUpOpen(true);
    setTimeout(() => {
      isLockedRef.current = false;
    }, 400);
  }, [isTopUpOpen, isPaywallOpen, isMilestoneOpen]);

  const closeTopUp = useCallback(() => {
    setIsTopUpOpen(false);
    setTopUpOptions({});
  }, []);

  const openMilestoneModal = useCallback((opts: MilestoneTriggerOptions = {}) => {
    if (isMilestoneOpen || isPaywallOpen || isTopUpOpen || isLockedRef.current) return;
    isLockedRef.current = true;
    setMilestoneOptions(opts);
    setIsMilestoneOpen(true);
    setTimeout(() => {
      isLockedRef.current = false;
    }, 400);
  }, [isMilestoneOpen, isPaywallOpen, isTopUpOpen]);

  const closeMilestoneModal = useCallback(() => {
    setIsMilestoneOpen(false);
    setMilestoneOptions({});
  }, []);

  // Paranoia Layer 1: Listen for global API Interceptor and milestone events
  useEffect(() => {
    const handleGlobalPaywallTrigger = (e: Event) => {
      const customEvent = e as CustomEvent<{
        type?: 'tier' | 'credits';
        reason?: string;
        featureName?: string;
        neededCredits?: number;
      }>;

      const detail = customEvent.detail || {};
      if (detail.type === 'credits') {
        openTopUp({
          neededCredits: detail.neededCredits,
          featureName: detail.featureName || 'Credit Balance',
        });
      } else {
        openPaywall({
          featureName: detail.featureName,
          reason: detail.reason,
          campaignName: 'Your Campaign',
        });
      }
    };

    const handleGlobalMilestoneTrigger = (e: Event) => {
      const customEvent = e as CustomEvent<MilestoneTriggerOptions>;
      openMilestoneModal(customEvent.detail || {});
    };

    window.addEventListener('elein:paywall-trigger', handleGlobalPaywallTrigger);
    window.addEventListener('elein:milestone-trigger', handleGlobalMilestoneTrigger);
    return () => {
      window.removeEventListener('elein:paywall-trigger', handleGlobalPaywallTrigger);
      window.removeEventListener('elein:milestone-trigger', handleGlobalMilestoneTrigger);
    };
  }, [openPaywall, openTopUp, openMilestoneModal]);

  const handlePaywallSuccess = useCallback(() => {
    // Paranoia Layer 1 & 2: Invalidate both canonical and any param-variant billing SWR keys app-wide
    mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein/billing/credits/balance'));
    mutate('/api/elein/workspaces/billing');
    mutate('/api/elein/billing/credits/balance');
    mutate('/api/elein/billing/history');
    if (paywallOptions.onSuccess) {
      paywallOptions.onSuccess();
    }
  }, [mutate, paywallOptions]);

  const handleTopUpSuccess = useCallback(() => {
    mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein/billing/credits/balance'));
    mutate('/api/elein/workspaces/billing');
    mutate('/api/elein/billing/credits/balance');
    mutate('/api/elein/billing/history');
    if (topUpOptions.onSuccess) {
      topUpOptions.onSuccess();
    }
  }, [mutate, topUpOptions]);

  const handleMilestoneSuccess = useCallback(() => {
    mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein/billing/credits/balance'));
    mutate('/api/elein/workspaces/billing');
    mutate('/api/elein/billing/credits/balance');
    mutate('/api/elein/billing/history');
    mutate('/api/elein/dashboard/stats');
    if (milestoneOptions.onSuccess) {
      milestoneOptions.onSuccess();
    }
  }, [mutate, milestoneOptions]);

  return (
    <PaywallContext.Provider
      value={{
        openPaywall,
        closePaywall,
        openTopUp,
        closeTopUp,
        openMilestoneModal,
        closeMilestoneModal,
        isPaywallOpen,
        isTopUpOpen,
        isMilestoneOpen,
      }}
    >
      {children}

      {/* Global In-Situ Paywall Modal */}
      <EleInPaywallModal
        isOpen={isPaywallOpen}
        onClose={closePaywall}
        campaignName={paywallOptions.campaignName || 'Your Outreach'}
        onSuccess={handlePaywallSuccess}
      />

      {/* Global In-Situ Micro-Monetization Top-Up Modal */}
      <CreditTopUpModal
        isOpen={isTopUpOpen}
        onClose={closeTopUp}
        currentBalance={currentCredits}
        onSuccess={handleTopUpSuccess}
      />

      {/* Global First-Win Milestone OTO Expansion Modal */}
      <FirstWinMilestoneModal
        isOpen={isMilestoneOpen}
        onClose={closeMilestoneModal}
        prospectName={milestoneOptions.prospectName}
        campaignName={milestoneOptions.campaignName}
        onSuccess={handleMilestoneSuccess}
      />
    </PaywallContext.Provider>
  );
};

export function usePaywall(): PaywallContextType {
  const context = useContext(PaywallContext);
  if (!context) {
    throw new Error('usePaywall must be used within a PaywallProvider');
  }
  return context;
}
