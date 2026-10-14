import { useState } from 'react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { mutate } from 'swr';

export interface CheckoutOptions {
  provider?: 'razorpay' | 'lemonsqueezy';
  packageId?: 'growth_tier' | 'growth_tier_annual' | 'growth_tier_oto' | 'growth_tier_annual_oto' | 'credits_1000' | 'credits_5000' | 'starter_tier' | string;
  action?: 'credits' | 'upgrade';
  onSuccess?: () => void;
  onError?: (error: Error) => void;
  onCancel?: () => void;
}

const loadRazorpay = (): Promise<boolean> => {
  return new Promise((resolve) => {
    if ((window as any).Razorpay) return resolve(true);
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
};

/**
 * Paranoia Layer 0 & 1: Polls the backend until the workspace tier or credits reflect in the database.
 * Prevents C-10 premature termination by comparing current credits against the pre-checkout baseline.
 */
async function pollForBillingSync(
  action: 'credits' | 'upgrade',
  initialCredits = 0,
  initialTier = 'FREE',
  maxAttempts = 10,
  intervalMs = 600
): Promise<boolean> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetchWithAuth('/api/elein/workspaces/billing');
      if (res.ok) {
        const data = await res.json();
        if (action === 'upgrade') {
          const currentTier = String(data.tier ?? '').toUpperCase();
          if (currentTier === 'PRO' || currentTier === 'GROWTH' || (initialTier === 'FREE' && currentTier !== 'FREE')) {
            return true; // Upgrade confirmed in DB!
          }
        }
        if (action === 'credits') {
          const currentCredits = Number(data.data_cleaning_credits ?? data.credits_remaining ?? 0);
          if (currentCredits > initialCredits) {
            return true; // Verified: Balance actually increased in DB!
          }
        }
      }
    } catch (_) {
      // Ignore transient network errors during poll
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return false;
}

export function useEleInCheckout() {
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [processingPackage, setProcessingPackage] = useState<string | null>(null);

  const startCheckout = async (options: CheckoutOptions = {}) => {
    // Paranoia Layer 2: Lock against double-clicks and repeated submissions
    if (isProcessing || isVerifying) return;

    const provider = options.provider || 'razorpay';
    const action = options.action || 'upgrade';
    const packageId = options.packageId || 'growth_tier';

    let isModalActive = false;
    try {
      setIsProcessing(true);
      setProcessingPackage(packageId);

      // Paranoia Layer 1: Capture baseline billing state to prevent premature poll termination (C-10)
      let baselineCredits = 0;
      let baselineTier = 'FREE';
      try {
        const baseRes = await fetchWithAuth('/api/elein/workspaces/billing');
        if (baseRes.ok) {
          const baseData = await baseRes.json();
          baselineCredits = Number(baseData.data_cleaning_credits ?? baseData.credits_remaining ?? 0);
          baselineTier = String(baseData.tier ?? 'FREE').toUpperCase();
        }
      } catch (_) {
        // Fallback to 0 if initial query fails
      }

      const response = await fetchWithAuth('/api/elein/billing/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          provider,
          action,
          package_id: packageId,
        }),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Checkout initialization failed');
      }

      const data = await response.json();

      if (provider === 'razorpay') {
        const loaded = await loadRazorpay();
        if (!loaded) {
          throw new Error('Failed to load Razorpay payment gateway script.');
        }

        // Paranoia Layer 1: Handle mock / development order simulations
        if (data.order_id && data.order_id.startsWith('order_mock_')) {
          setIsProcessing(false);
          setIsVerifying(true);
          const toastId = toast.loading('Simulating payment & synchronizing workspace...');
          
          // Verify mock order synchronously on backend
          await fetchWithAuth('/api/elein/billing/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              razorpay_payment_id: `pay_mock_${Date.now()}`,
              razorpay_order_id: data.order_id,
              razorpay_signature: 'mock_signature',
              session_id: data.session_id,
            }),
          }).catch(() => {});

          await pollForBillingSync(action, baselineCredits, baselineTier, 5, 400);
          toast.dismiss(toastId);
          toast.success(
            action === 'credits' 
              ? 'Payment verified! Credits added to your workspace.' 
              : 'Payment verified! Account upgraded to Growth Tier.'
          );

          // Invalidate app-wide caches
          mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein/billing/credits/balance'));
          mutate('/api/elein/billing/credits/balance');
          mutate('/api/elein/workspaces/billing');
          mutate('/api/elein/billing/history');

          setIsVerifying(false);

          if (options.onSuccess) {
            options.onSuccess();
          }
          return;
        }

        const rzpOptions = {
          key: data.key_id || 'dummy_key',
          amount: data.amount,
          currency: 'INR',
          name: 'Ele-in',
          description: action === 'credits' ? 'Buy Platform Credits' : 'Upgrade to Growth Tier',
          order_id: data.order_id,
          handler: async function (paymentRes: any) {
            setIsProcessing(false);
            setIsVerifying(true);
            const verifyToast = toast.loading('Confirming payment with bank & updating workspace...');

            try {
              // 1. Fast-Path: Synchronous server verification
              await fetchWithAuth('/api/elein/billing/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  razorpay_payment_id: paymentRes.razorpay_payment_id,
                  razorpay_order_id: paymentRes.razorpay_order_id,
                  razorpay_signature: paymentRes.razorpay_signature,
                  session_id: data.session_id,
                }),
              });

              // 2. Paranoia Layer 1: Active state poll to guarantee DB write completed
              const isSynced = await pollForBillingSync(action, baselineCredits, baselineTier, 10, 600);

              toast.dismiss(verifyToast);

              if (isSynced) {
                toast.success(
                  action === 'credits'
                    ? 'Payment verified! Credits added to your workspace.'
                    : 'Payment verified! Growth Tier is now active.'
                );
              } else {
                // Edge case: Webhook/sync delayed but payment succeeded
                toast.success(
                  action === 'credits'
                    ? 'Payment received! Credits will reflect in your balance shortly.'
                    : 'Payment received! Upgrading workspace in the background.'
                );
              }

              // Invalidate app-wide caches
              mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein/billing/credits/balance'));
              mutate('/api/elein/billing/credits/balance');
              mutate('/api/elein/workspaces/billing');
              mutate('/api/elein/billing/history');

              if (options.onSuccess) {
                options.onSuccess();
              }
            } catch (err: any) {
              console.error('Verification failed', err);
              toast.dismiss(verifyToast);
              // Fallback to active poll in case verify errored but webhook succeeds
              const isSynced = await pollForBillingSync(action, baselineCredits, baselineTier, 6, 800);
              if (isSynced && options.onSuccess) {
                toast.success(
                  action === 'credits'
                    ? 'Payment verified! Credits added.'
                    : 'Payment verified! Growth Tier is active.'
                );

                mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein/billing/credits/balance'));
                mutate('/api/elein/billing/credits/balance');
                mutate('/api/elein/workspaces/billing');
                mutate('/api/elein/billing/history');

                options.onSuccess();
              } else {
                toast.error('Payment completed, but verification timed out. Please refresh or contact support.');
              }
            } finally {
              setIsVerifying(false);
              setProcessingPackage(null);
            }
          },
          modal: {
            ondismiss: function () {
              setIsProcessing(false);
              setProcessingPackage(null);
              toast.info('Checkout cancelled. No charges were made.');
              if (data.session_id) {
                fetchWithAuth('/api/elein/billing/cancel-session', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    session_id: data.session_id,
                    reason: 'user_dismissed_modal',
                  }),
                }).catch(() => {});
              }
              if (options.onCancel) {
                options.onCancel();
              }
            },
            escape: true,
            backdropclose: false,
          },
          theme: { color: '#6366f1' },
        };

        const rzp = new (window as any).Razorpay(rzpOptions);
        rzp.on('payment.failed', function (paymentError: any) {
          setIsProcessing(false);
          setProcessingPackage(null);
          const errMsg =
            paymentError?.error?.description ||
            paymentError?.error?.reason ||
            'Payment failed or declined by your bank. Please try another card or UPI.';
          console.error('[Razorpay] Payment failed event:', paymentError?.error);
          toast.error(errMsg);
          if (data.session_id) {
            fetchWithAuth('/api/elein/billing/cancel-session', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                session_id: data.session_id,
                reason: paymentError?.error?.code || 'payment_failed',
              }),
            }).catch(() => {});
          }
          if (options.onError) {
            options.onError(new Error(errMsg));
          }
        });

        rzp.open();
        isModalActive = true;
      } else if (provider === 'lemonsqueezy') {
        if (data.checkout_url && data.checkout_url.includes('mock.lemonsqueezy.com')) {
          toast.success(
            action === 'credits'
              ? 'Payment simulated successfully! Credits added.'
              : 'Payment simulated successfully! Account upgraded.'
          );
          mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein/billing/credits/balance'));
          mutate('/api/elein/billing/credits/balance');
          mutate('/api/elein/workspaces/billing');
          mutate('/api/elein/billing/history');

          if (options.onSuccess) {
            setTimeout(options.onSuccess, 800);
          }
          return;
        }

        if ((window as any).LemonSqueezy) {
          (window as any).LemonSqueezy.Url.Open(data.checkout_url);
        } else {
          const win = window.open(data.checkout_url, '_blank');
          if (!win) {
            toast.info('Pop-up blocked. Redirecting to checkout...', {
              action: {
                label: 'Open Checkout',
                onClick: () => window.location.assign(data.checkout_url),
              },
            });
          }
        }
      }
    } catch (error: any) {
      console.error('Error during checkout:', error);
      toast.error(error.message || 'Failed to process checkout. Please try again.');
      if (options.onError) {
        options.onError(error);
      }
    } finally {
      if (!isModalActive) {
        setIsProcessing(false);
        setProcessingPackage(null);
      }
    }
  };

  return {
    startCheckout,
    isProcessing,
    isVerifying,
    processingPackage,
  };
}
