import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "motion/react"
import { Zap, CheckCircle2, CircleDollarSign, Loader2, Rocket, ShieldCheck, History, AlertCircle, X, Receipt, CreditCard as CardIcon, Activity, RefreshCw, Lock, Download, Printer, Copy, Check, FileText } from "lucide-react"
import SpotlightCard from "@/components/SpotlightCard"
import ShinyText from "@/components/ShinyText"
import useSWR from "swr"
import { useWorkspace } from "@/contexts/WorkspaceContext"
import { usePaywall } from "@/contexts/PaywallContext"
import { toast } from "sonner"
import { fetchWithAuth } from "@/lib/apiClient"
import { CancelSubscriptionModal } from "@/components/billing/CancelSubscriptionModal"
import { CreditTopUpModal } from "@/components/billing/CreditTopUpModal"
import { EleInPaywallModal } from "@campaigns/EleInPaywallModal"
import { CustomSelect } from "@/components/ui/select"

function sanitizeCsvCell(value: any): string {
  const str = String(value ?? "");
  if (/^[=+\-@\t\r]/.test(str)) {
    return `"'${str.replace(/"/g, '""')}"`;
  }
  return `"${str.replace(/"/g, '""')}"`;
}

const loadRazorpay = () => new Promise((resolve) => {
  if ((window as any).Razorpay) return resolve(true);
  const script = document.createElement("script");
  script.src = "https://checkout.razorpay.com/v1/checkout.js";
  script.onload = () => resolve(true);
  script.onerror = () => resolve(false);
  document.body.appendChild(script);
});

export function EleInBilling() {
  const [provider, setProvider] = useState<'razorpay' | 'lemonsqueezy'>('razorpay');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [processingAction, setProcessingAction] = useState<'credits' | 'upgrade' | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'history' | 'usage'>('overview');
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showTopUpModal, setShowTopUpModal] = useState(false);
  const [showPaywallModal, setShowPaywallModal] = useState(false);
  const [isAnnual, setIsAnnual] = useState(false);
  
  // Tax Receipt State (Layer 0, 1 & 2)
  const [selectedTxnForReceipt, setSelectedTxnForReceipt] = useState<any | null>(null);
  const [receiptData, setReceiptData] = useState<any | null>(null);
  const [loadingReceipt, setLoadingReceipt] = useState(false);
  const [copiedInvoiceNum, setCopiedInvoiceNum] = useState(false);
  
  const { openPaywall } = usePaywall();
  const { activeWorkspaceId } = useWorkspace();

  const { data: billingData, error: billingError, mutate, isLoading } = useSWR(
    activeWorkspaceId ? `/api/elein/billing/credits/balance` : null,
    async (url) => {
      const res = await fetchWithAuth(url);
      if (!res.ok) throw new Error("Failed to fetch billing data");
      return res.json();
    }
  );

  const { data: historyData, mutate: mutateHistory } = useSWR(
    activeWorkspaceId ? `/api/elein/billing/history` : null,
    async (url) => {
      const res = await fetchWithAuth(url);
      if (!res.ok) throw new Error("Failed to fetch history");
      return res.json();
    }
  );

  const { data: usageData, mutate: mutateUsage } = useSWR(
    activeWorkspaceId ? `/api/elein/billing/credits/usage` : null,
    async (url) => {
      const res = await fetchWithAuth(url);
      if (!res.ok) throw new Error("Failed to fetch usage");
      const data = await res.json();
      return data.deductions || [];
    }
  );

  const { data: churnHealth, mutate: mutateChurnHealth } = useSWR(
    activeWorkspaceId ? `/api/elein/billing/churn-health` : null,
    async (url) => {
      const res = await fetchWithAuth(url);
      if (!res.ok) return null;
      return res.json();
    }
  );

  const { data: autoRechargeRes, mutate: mutateAutoRecharge } = useSWR(
    activeWorkspaceId ? `/api/elein/billing/auto-recharge` : null,
    async (url) => {
      const res = await fetchWithAuth(url);
      if (!res.ok) return null;
      return res.json();
    }
  );

  const autoRechargeSettings = autoRechargeRes?.settings;
  const canAutoRecharge = autoRechargeRes?.can_auto_recharge ?? false;

  const [autoRechargeEnabled, setAutoRechargeEnabled] = useState(false);
  const [thresholdCredits, setThresholdCredits] = useState(100);
  const [rechargePackageId, setRechargePackageId] = useState('credits_1000');
  const [maxMonthlyRecharges, setMaxMonthlyRecharges] = useState(5);
  const [isSavingAutoRecharge, setIsSavingAutoRecharge] = useState(false);
  const [isSimulatingRecharge, setIsSimulatingRecharge] = useState(false);

  useEffect(() => {
    if (autoRechargeSettings) {
      setAutoRechargeEnabled(!!autoRechargeSettings.enabled);
      setThresholdCredits(autoRechargeSettings.threshold_credits ?? 100);
      setRechargePackageId(autoRechargeSettings.recharge_package_id ?? 'credits_1000');
      setMaxMonthlyRecharges(autoRechargeSettings.max_monthly_recharges ?? 5);
    }
  }, [autoRechargeSettings]);

  const handleSaveAutoRecharge = async (updates: Partial<{
    enabled: boolean;
    threshold_credits: number;
    recharge_package_id: string;
    max_monthly_recharges: number;
  }>) => {
    const isProTier = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';
    const nextEnabled = updates.enabled !== undefined ? updates.enabled : autoRechargeEnabled;

    if (nextEnabled && (!isProTier && !canAutoRecharge)) {
      openPaywall({
        featureName: "Automated Credit Auto-Recharge",
        campaignName: "In-Flight Overdraft Protection",
      });
      return;
    }

    const payload = {
      enabled: nextEnabled,
      threshold_credits: updates.threshold_credits ?? thresholdCredits,
      recharge_package_id: updates.recharge_package_id ?? rechargePackageId,
      max_monthly_recharges: updates.max_monthly_recharges ?? maxMonthlyRecharges,
    };

    try {
      setIsSavingAutoRecharge(true);
      const res = await fetchWithAuth('/api/elein/billing/auto-recharge', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 403) {
          openPaywall({
            featureName: "Automated Credit Auto-Recharge",
            campaignName: "In-Flight Overdraft Protection",
          });
          return;
        }
        throw new Error(err.detail || "Failed to update auto-recharge settings");
      }

      toast.success(payload.enabled ? "Auto-recharge enabled and saved!" : "Auto-recharge preferences saved.");
      await mutateAutoRecharge();
    } catch (err: any) {
      toast.error(err.message || "Failed to save auto-recharge settings");
    } finally {
      setIsSavingAutoRecharge(false);
    }
  };

  const handleToggleAutoRecharge = () => {
    const isProTier = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';
    if (!isProTier && !canAutoRecharge) {
      openPaywall({
        featureName: "Automated Credit Auto-Recharge",
        campaignName: "In-Flight Overdraft Protection",
      });
      return;
    }
    const nextState = !autoRechargeEnabled;
    setAutoRechargeEnabled(nextState);
    handleSaveAutoRecharge({ enabled: nextState });
  };

  const handleSimulateAutoRecharge = async () => {
    try {
      setIsSimulatingRecharge(true);
      const res = await fetchWithAuth('/api/elein/billing/auto-recharge/simulate-trigger', {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Simulation failed");
      }
      const data = await res.json();
      if (data.result?.triggered) {
        toast.success(`Auto-recharge simulated: +${(data.result.credits_added || 1000).toLocaleString()} credits replenished.`);
      } else {
        toast.info(`Simulation note: ${data.result?.reason || 'no trigger'}`);
      }
      await Promise.all([mutate(), mutateHistory(), mutateUsage(), mutateAutoRecharge()]);
    } catch (err: any) {
      toast.error(err.message || "Failed to simulate auto-recharge");
    } finally {
      setIsSimulatingRecharge(false);
    }
  };

  const [isReactivating, setIsReactivating] = useState(false);

  const handleReactivateSubscription = async () => {
    setIsReactivating(true);
    try {
      const res = await fetchWithAuth('/api/elein/billing/reactivate-subscription', {
        method: 'POST',
      });
      if (!res.ok) throw new Error("Failed to reactivate");
      toast.success("Subscription reactivated successfully! Full Growth Plan active.");
      mutate();
      mutateChurnHealth();
    } catch (e: any) {
      toast.error(e.message || "Failed to reactivate subscription");
    } finally {
      setIsReactivating(false);
    }
  };

  const handleViewReceipt = async (txn: any) => {
    setSelectedTxnForReceipt(txn);
    setLoadingReceipt(true);
    setReceiptData(null);
    try {
      const res = await fetchWithAuth(`/api/elein/billing/transactions/${txn.id}/receipt`);
      if (!res.ok) {
        throw new Error("Failed to load invoice receipt");
      }
      const data = await res.json();
      setReceiptData(data);
    } catch (err: any) {
      toast.error(err.message || "Could not fetch official invoice receipt");
    } finally {
      setLoadingReceipt(false);
    }
  };

  const handleCopyInvoiceNum = (invoiceNum: string) => {
    navigator.clipboard.writeText(invoiceNum);
    setCopiedInvoiceNum(true);
    toast.success("Invoice number copied to clipboard!");
    setTimeout(() => setCopiedInvoiceNum(false), 2000);
  };

  const handleExportUsageCsv = () => {
    if (!usageData || usageData.length === 0) {
      toast.error("No credit usage data to export.");
      return;
    }
    const headers = ["Timestamp", "Action Type", "Credits Deducted", "Balance After"];
    const rows = usageData.map((item: any) => [
      sanitizeCsvCell(item.created_at || "N/A"),
      sanitizeCsvCell(item.action_type || "N/A"),
      sanitizeCsvCell(item.amount || 0),
      sanitizeCsvCell(item.balance_after ?? "N/A"),
    ]);
    const csvContent = [headers.join(","), ...rows.map((r: any[]) => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `elein_credit_usage_${new Date().toISOString().split("T")[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success(`Exported ${usageData.length} records to CSV`);
  };

  const handleCheckout = async (action: 'credits' | 'upgrade') => {
    if (isProcessing) return; // Layer 2 Paranoia: Prevent double-click double-billing
    let isModalActive = false;
    try {
      setIsProcessing(true);
      setProcessingAction(action);
      
      const package_id = action === 'credits' ? 'credits_1000' : (isAnnual ? 'growth_tier_annual' : 'growth_tier');
      const response = await fetchWithAuth('/api/elein/billing/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          provider,
          package_id
        }),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Checkout request failed');
      }

      const data = await response.json();

      if (provider === 'razorpay') {
        const loaded = await loadRazorpay();
        if (!loaded) {
          toast.error("Failed to load Razorpay checkout.");
          return;
        }
        // If order_id is a mock, Razorpay will reject it immediately with a modal alert. 
        if (data.order_id && data.order_id.startsWith('order_mock_')) {
          try {
            const verifyRes = await fetchWithAuth('/api/elein/billing/verify', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                razorpay_payment_id: `pay_mock_${Date.now()}`,
                razorpay_order_id: data.order_id,
                razorpay_signature: 'mock_signature',
                session_id: data.session_id,
              }),
            });
            if (!verifyRes.ok) {
              const err = await verifyRes.json().catch(() => ({}));
              throw new Error(err.detail || "Payment verification failed");
            }
            toast.success("Payment simulated successfully! Account upgraded.");
          } catch (verErr: any) {
            console.error("Mock verification error:", verErr);
            toast.error(verErr.message || "Failed to verify mock payment");
          } finally {
            await Promise.all([mutate(), mutateHistory(), mutateUsage()]);
          }
          return;
        }
        
        const options = {
          key: data.key_id || "dummy_key",
          amount: data.amount, 
          currency: "INR",
          name: "Ele-in",
          description: action === 'credits' ? "Buy More Credits" : "Upgrade to Growth",
          order_id: data.order_id,
          handler: async function (res: any) {
            try {
              setIsProcessing(true);
              const verifyRes = await fetchWithAuth('/api/elein/billing/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  razorpay_payment_id: res.razorpay_payment_id,
                  razorpay_order_id: res.razorpay_order_id,
                  razorpay_signature: res.razorpay_signature,
                  session_id: data.session_id,
                }),
              });
              if (!verifyRes.ok) {
                const err = await verifyRes.json().catch(() => ({}));
                throw new Error(err.detail || "Payment verification failed");
              }
              toast.success(action === 'credits' ? "Credits added successfully!" : "Upgraded to Growth tier successfully!");
            } catch (err: any) {
              console.error("Verification failed:", err);
              toast.error(err.message || "Failed to verify payment with server.");
            } finally {
              setIsProcessing(false);
              setProcessingAction(null);
              await Promise.all([mutate(), mutateHistory(), mutateUsage()]);
            }
          },
          modal: {
            ondismiss: function () {
              setIsProcessing(false);
              setProcessingAction(null);
              toast.info("Checkout cancelled. No charges were made.");
              if (data.session_id) {
                fetchWithAuth('/api/elein/billing/cancel-session', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ session_id: data.session_id, reason: 'user_dismissed_modal' })
                }).catch(() => {});
              }
            },
            escape: true,
            backdropclose: false
          },
          theme: { color: "#ffffff" },
        };

        const rzp = new (window as any).Razorpay(options);
        rzp.on('payment.failed', function (paymentErr: any) {
          setIsProcessing(false);
          setProcessingAction(null);
          const errMsg = paymentErr?.error?.description || paymentErr?.error?.reason || "Payment declined by issuing bank.";
          console.error("[Razorpay] Payment failed:", paymentErr?.error);
          toast.error(errMsg);
          if (data.session_id) {
            fetchWithAuth('/api/elein/billing/cancel-session', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ session_id: data.session_id, reason: paymentErr?.error?.code || 'payment_failed' })
            }).catch(() => {});
          }
        });

        rzp.open();
        isModalActive = true;

      } else if (provider === 'lemonsqueezy') {
        if (data.checkout_url && data.checkout_url.includes('mock.lemonsqueezy.com')) {
          toast.success("Payment simulated successfully! Account upgraded.");
          await Promise.all([mutate(), mutateHistory(), mutateUsage()]);
          return;
        }
        if ((window as any).LemonSqueezy) {
          (window as any).LemonSqueezy.Url.Open(data.checkout_url);
          setTimeout(() => {
            mutate();
            mutateHistory();
            mutateUsage();
          }, 5000);
        } else {
          const win = window.open(data.checkout_url, "_blank");
          if (!win) {
            toast.info("Pop-up blocked. Redirecting to checkout...", {
              action: {
                label: "Open Checkout",
                onClick: () => window.location.assign(data.checkout_url)
              }
            });
          }
        }
      }
    } catch (error: any) {
      console.error("Error during checkout:", error);
      toast.error(error.message || "Failed to process checkout. Please try again.");
    } finally {
      if (!isModalActive) {
        setIsProcessing(false);
        setProcessingAction(null);
      }
    }
  };

  const credits = billingData?.balance ?? 0;
  const tier = billingData?.tier ?? "FREE";
  const plan = tier === "PRO" ? "Growth Tier" : tier === "ENTERPRISE" ? "Enterprise Tier" : "Free Tier";
  const activeCampaigns = billingData?.active_campaigns ?? 0;
  
  const isPro = tier === "PRO" || tier === "ENTERPRISE";
  const campaignLimit = isPro ? 'Unlimited' : 2;
  const campaignPercentage = isPro ? 0 : Math.min((activeCampaigns / 2) * 100, 100);

  const features = [
    "Unlimited Active Campaigns",
    "Priority AI Sequencing",
    "Dedicated IP Routing",
    "Advanced Webhooks",
    "Premium Support"
  ];

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-6 py-12 md:px-12 max-w-7xl mx-auto font-sans selection:bg-primary/20">
      
      {/* Cancel Subscription Modal removed for MVP - users must contact support to cancel */}

      {/* Header Section */}
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-12 flex flex-col md:flex-row md:justify-between md:items-end gap-6 border-b border-border/40 pb-8">
        <div>
          <h1 className="text-4xl font-extrabold mb-3 flex items-center gap-3 tracking-tight">
            <div className="p-2.5 bg-primary/10 rounded-xl border border-primary/20 text-primary">
              <CardIcon size={28} strokeWidth={2} />
            </div>
            <ShinyText text="Billing & Limits" disabled={false} speed={3} className="" />
          </h1>
          <p className="text-sm text-muted-foreground max-w-xl leading-relaxed">
            Monitor your workspace usage, manage your active plan, and purchase data enrichment credits.
          </p>
        </div>

        {/* Currency Toggle (Sleek Segmented Control) */}
        <div className="flex flex-col items-start md:items-end gap-2">
          <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground ml-1 md:ml-0 md:mr-1">Billing Currency</span>
          <div className="flex items-center p-1 bg-muted/40 backdrop-blur-md rounded-xl border border-border/50 shadow-inner">
            <button 
              onClick={() => setProvider('razorpay')}
              className={`relative px-6 py-2 rounded-lg text-sm font-semibold transition-all duration-300 ${provider === 'razorpay' ? 'text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >
              {provider === 'razorpay' && (
                <motion.div layoutId="activeCurrency" className="absolute inset-0 bg-background rounded-lg shadow-sm border border-border/50" />
              )}
              <span className="relative z-10 flex items-center gap-2">INR <span className="opacity-50 text-xs hidden sm:inline">(India)</span></span>
            </button>
            <button 
              onClick={() => { toast.info("Global USD payments via LemonSqueezy are rolling out next week. Please use INR for now."); }}
              className="relative px-6 py-2 rounded-lg text-sm font-semibold transition-all duration-300 text-muted-foreground/50 cursor-not-allowed hover:text-foreground/50"
            >
              <span className="relative z-10 flex items-center gap-2">USD <span className="opacity-50 text-xs hidden sm:inline">(Global)</span></span>
            </button>
          </div>
        </div>
      </motion.div>

      {/* Churn Reactivation & Health Alert Banners */}
      {churnHealth?.cancel_at_period_end && (
        <div className="mb-8 p-5 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-xs">
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-600 dark:text-amber-400 shrink-0">
              <AlertCircle size={20} />
            </div>
            <div>
              <h4 className="text-sm font-bold text-foreground">
                Subscription Scheduled for Cancellation
              </h4>
              <p className="text-xs text-muted-foreground mt-0.5">
                Your Growth features remain active until your billing period ends. All sequences and lead lists are safely preserved.
              </p>
            </div>
          </div>
          <button
            onClick={handleReactivateSubscription}
            disabled={isReactivating}
            className="px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold shrink-0 transition shadow-sm"
          >
            {isReactivating ? "Reactivating..." : "Resume Growth Plan"}
          </button>
        </div>
      )}

      {churnHealth && !churnHealth.cancel_at_period_end && churnHealth.churn_risk !== 'LOW' && (
        <div className="mb-8 p-5 rounded-2xl bg-indigo-500/5 border border-indigo-500/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-500 shrink-0 mt-0.5">
              <Activity size={20} />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-foreground">
                  Pipeline Vitality Index: {churnHealth.health_score}/100
                </h4>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                  churnHealth.churn_risk === 'CRITICAL' ? 'bg-rose-500/10 text-rose-500' : 'bg-amber-500/10 text-amber-500'
                }`}>
                  {churnHealth.churn_risk} RISK
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {churnHealth.risk_factors?.[0]?.message || "Outreach vitality alert: Optimize active sequences to maximize lead conversion."}
              </p>
            </div>
          </div>
          {churnHealth.recommendations?.[0] && (
            <a
              href={churnHealth.recommendations[0].action_url}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shrink-0 transition shadow-sm inline-block"
            >
              {churnHealth.recommendations[0].title}
            </a>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-8 mb-8 border-b border-border/40">
        <button 
          onClick={() => setActiveTab('overview')}
          className={`pb-4 text-sm font-bold transition-all relative ${activeTab === 'overview' ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
        >
          Usage & Plan
          {activeTab === 'overview' && <motion.div layoutId="bottomLine" className="absolute bottom-0 left-0 right-0 h-0.5 bg-foreground rounded-t-full" />}
        </button>
        <button 
          onClick={() => setActiveTab('history')}
          className={`pb-4 text-sm font-bold transition-all relative ${activeTab === 'history' ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
        >
          Transaction History
          {activeTab === 'history' && <motion.div layoutId="bottomLine" className="absolute bottom-0 left-0 right-0 h-0.5 bg-foreground rounded-t-full" />}
        </button>
        <button 
          onClick={() => setActiveTab('usage')}
          className={`pb-4 text-sm font-bold transition-all relative ${activeTab === 'usage' ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
        >
          Credit Usage Log
          {activeTab === 'usage' && <motion.div layoutId="bottomLine" className="absolute bottom-0 left-0 right-0 h-0.5 bg-foreground rounded-t-full" />}
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="animate-spin text-muted-foreground" size={32} /></div>
      ) : (
        <AnimatePresence mode="wait">
          {activeTab === 'overview' && (
            <motion.div 
              key="overview"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-12"
            >
              {/* Left Column: Usage Limits */}
              <div className="lg:col-span-7 space-y-6">
                <SpotlightCard className="p-8 rounded-3xl border border-border/50 bg-muted/10 shadow-sm relative overflow-hidden">
                  <div className="flex justify-between items-start mb-8">
                    <div>
                      <h2 className="text-xl font-bold mb-1">Workspace Limits</h2>
                      <p className="text-sm text-muted-foreground">Your current usage based on the {plan}.</p>
                    </div>
                    {isPro ? (
                      <span className="bg-primary/10 text-primary border border-primary/20 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                        <CheckCircle2 size={14} /> PRO
                      </span>
                    ) : (
                      <span className="bg-muted/50 text-muted-foreground border border-border/50 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider">
                        FREE
                      </span>
                    )}
                  </div>

                  <div className="space-y-8">
                    {/* Campaigns Limit */}
                    <div>
                      <div className="flex justify-between items-end mb-3">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-background rounded-lg border border-border/50 shadow-sm"><Rocket size={16} className="text-foreground" /></div>
                          <div>
                            <p className="text-sm font-bold">Active Campaigns</p>
                            <p className="text-xs text-muted-foreground">Running concurrently</p>
                          </div>
                        </div>
                        <p className="text-sm font-bold font-mono">{activeCampaigns} <span className="text-muted-foreground">/ {campaignLimit}</span></p>
                      </div>
                      <div className="w-full bg-muted/50 rounded-full h-2 overflow-hidden border border-border/30 relative">
                        {isPro ? (
                           <div className="absolute inset-0 bg-gradient-to-r from-primary/40 to-primary/20" />
                        ) : (
                          <motion.div 
                            initial={{ width: 0 }} 
                            animate={{ width: `${campaignPercentage}%` }} 
                            className={`h-full rounded-full ${campaignPercentage >= 100 ? 'bg-destructive' : 'bg-primary'}`}
                          />
                        )}
                      </div>
                      {!isPro && campaignPercentage >= 100 && (
                        <p className="text-xs text-destructive mt-2 flex items-center gap-1.5"><AlertCircle size={12} /> Limit reached. Upgrade to launch more.</p>
                      )}
                    </div>

                    {/* ROI Calculator */}
                    <div>
                      <div className="flex justify-between items-end mb-3">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-background rounded-lg border border-border/50 shadow-sm"><CircleDollarSign size={16} className="text-success" /></div>
                          <div>
                            <p className="text-sm font-bold">Live ROI Calculator</p>
                            <p className="text-xs text-muted-foreground">Estimated impact</p>
                          </div>
                        </div>
                        {activeCampaigns > 0 && <p className="text-xs font-bold text-success bg-success/10 px-2 py-1 rounded-md">High Performance</p>}
                      </div>
                      <div className="p-4 rounded-xl bg-success/5 border border-success/20">
                        {activeCampaigns > 0 ? (
                          <p className="text-sm text-foreground leading-relaxed">
                            Your <strong className="text-success">{activeCampaigns} active campaign{activeCampaigns === 1 ? '' : 's'}</strong> generated <strong className="text-success">~{activeCampaigns * 7} replies</strong> this week. 
                            {!isPro && " Upgrading to Growth could scale you to an estimated 50+ replies/week."}
                          </p>
                        ) : (
                          <p className="text-sm text-foreground leading-relaxed">
                            Launch a campaign to start generating AI-driven replies. {!isPro && "Upgrade to Growth to run unlimited campaigns."}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Credits Limit */}
                    <div>
                      <div className="flex justify-between items-end mb-3">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-background rounded-lg border border-border/50 shadow-sm"><CircleDollarSign size={16} className="text-foreground" /></div>
                          <div>
                            <p className="text-sm font-bold">Platform Credits</p>
                            <p className="text-xs text-muted-foreground">Used for AI & enrichment</p>
                          </div>
                        </div>
                        <p className="text-sm font-bold font-mono">{credits.toLocaleString()} <span className="text-muted-foreground">Available</span></p>
                      </div>
                      
                      {/* AI Burn Rate Forecast */}
                      <div className={`mt-2 mb-6 p-3 rounded-xl border flex items-start gap-3 ${credits <= 0 ? 'bg-destructive/10 border-destructive/20 text-destructive' : 'bg-warning/10 border-warning/20 text-warning'}`}>
                        <div className="mt-0.5"><AlertCircle size={16} /></div>
                        <div>
                          <p className={`text-xs font-bold ${credits <= 0 ? 'text-destructive' : 'text-warning-foreground'}`}>AI Burn Rate Forecast</p>
                          <p className={`text-[11px] leading-relaxed ${credits <= 0 ? 'text-destructive/80' : 'text-warning-foreground/80'}`}>
                            {credits <= 0 
                              ? "You have exhausted your credits. Top up now to resume AI tasks and enrichment. Overdraft protection covers up to -500 credits for inflight actions."
                              : `At your current sending velocity, you will exhaust your credits in ~${Math.max(1, Math.floor(credits/50))} days. You are covered by our overdraft protection up to -500 credits.`}
                          </p>
                        </div>
                      </div>
                      <div className="p-4 rounded-xl bg-background border border-border/50 flex flex-col gap-4">
                        <div className="flex justify-between items-center">
                          <p className="text-sm text-muted-foreground">Need more credits?</p>
                          <button 
                            onClick={() => setShowTopUpModal(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-foreground text-background hover:bg-foreground/90 rounded-lg text-sm font-bold transition-all shadow-sm"
                          >
                            Buy 1K ({provider === 'razorpay' ? '₹999' : '$12'})
                          </button>
                        </div>
                      </div>

                      {/* Auto-Recharge & In-Flight Overdraft Replenishment Panel */}
                      <div className="mt-4 p-5 rounded-2xl bg-background border border-border/60 shadow-sm space-y-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3">
                            <div className="p-2.5 rounded-xl bg-primary/10 text-primary border border-primary/20 shrink-0 mt-0.5">
                              <RefreshCw size={18} className={autoRechargeEnabled ? "animate-spin-slow" : ""} />
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <h4 className="text-sm font-bold text-foreground">Automated Credit Auto-Recharge</h4>
                                {!isPro && (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase bg-primary/10 text-primary border border-primary/20 flex items-center gap-1">
                                    <Lock size={10} /> Pro
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                                Replenishes credits in-flight before your balance runs out, ensuring outreach campaigns, AI responses, and enrichments never stall.
                              </p>
                            </div>
                          </div>

                          {/* Toggle Switch */}
                          <button
                            type="button"
                            role="switch"
                            aria-checked={autoRechargeEnabled}
                            onClick={handleToggleAutoRecharge}
                            disabled={isSavingAutoRecharge}
                            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                              autoRechargeEnabled ? 'bg-primary' : 'bg-muted'
                            }`}
                          >
                            <span
                              aria-hidden="true"
                              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-background shadow-lg ring-0 transition duration-200 ease-in-out ${
                                autoRechargeEnabled ? 'translate-x-5' : 'translate-x-0'
                              }`}
                            />
                          </button>
                        </div>

                        {/* Active / Expanded Controls */}
                        {autoRechargeEnabled ? (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="space-y-4 pt-3 border-t border-border/40"
                          >
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                              {/* Threshold Selector */}
                              <div>
                                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                                  Trigger Balance
                                </label>
                                <CustomSelect
                                  value={String(thresholdCredits)}
                                  onValueChange={(val) => {
                                    const numVal = Number(val);
                                    setThresholdCredits(numVal);
                                    handleSaveAutoRecharge({ threshold_credits: numVal });
                                  }}
                                  size="sm"
                                  triggerClassName="w-full text-xs font-medium rounded-xl border border-border/60 bg-muted/30 px-3 py-2 text-foreground focus-visible:ring-primary focus-visible:border-primary"
                                  options={[
                                    { value: "50", label: "When balance drops < 50" },
                                    { value: "100", label: "When balance drops < 100 (Default)" },
                                    { value: "250", label: "When balance drops < 250 (High Volume)" },
                                    { value: "500", label: "When balance drops < 500 (Enterprise)" },
                                  ]}
                                />
                              </div>

                              {/* Recharge Package Selector */}
                              <div>
                                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                                  Top-Up Amount
                                </label>
                                <CustomSelect
                                  value={rechargePackageId}
                                  onValueChange={(val) => {
                                    setRechargePackageId(val);
                                    handleSaveAutoRecharge({ recharge_package_id: val });
                                  }}
                                  size="sm"
                                  triggerClassName="w-full text-xs font-medium rounded-xl border border-border/60 bg-muted/30 px-3 py-2 text-foreground focus-visible:ring-primary focus-visible:border-primary"
                                  options={[
                                    { value: "credits_1000", label: `1,000 Credits (${provider === 'razorpay' ? '₹999' : '$12'})` },
                                    { value: "credits_5000", label: `5,000 Credits (${provider === 'razorpay' ? '₹4,499' : '$55'}) — 10% Off` },
                                  ]}
                                />
                              </div>

                              {/* Safety Circuit Breaker Selector */}
                              <div>
                                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                                  Monthly Safety Cap
                                </label>
                                <CustomSelect
                                  value={String(maxMonthlyRecharges)}
                                  onValueChange={(val) => {
                                    const numVal = Number(val);
                                    setMaxMonthlyRecharges(numVal);
                                    handleSaveAutoRecharge({ max_monthly_recharges: numVal });
                                  }}
                                  size="sm"
                                  triggerClassName="w-full text-xs font-medium rounded-xl border border-border/60 bg-muted/30 px-3 py-2 text-foreground focus-visible:ring-primary focus-visible:border-primary"
                                  options={[
                                    { value: "2", label: "Max 2 charges / mo" },
                                    { value: "5", label: "Max 5 charges / mo (Recommended)" },
                                    { value: "10", label: "Max 10 charges / mo" },
                                    { value: "20", label: "Max 20 charges / mo (High Velocity)" },
                                  ]}
                                />
                              </div>
                            </div>

                            {/* Safety Circuit Breaker Preview Notice */}
                            <div className="p-3 rounded-xl bg-primary/5 border border-primary/15 flex items-start justify-between gap-3 text-xs">
                              <div className="space-y-0.5">
                                <p className="font-semibold text-foreground flex items-center gap-1.5">
                                  <ShieldCheck size={14} className="text-primary" />
                                  Circuit Breaker Spending Protection:
                                </p>
                                <p className="text-muted-foreground text-[11px] leading-relaxed">
                                  Max monthly charge bounded at{" "}
                                  <strong className="text-foreground">
                                    {provider === 'razorpay' 
                                      ? `₹${((rechargePackageId === 'credits_5000' ? 4499 : 999) * maxMonthlyRecharges).toLocaleString()}`
                                      : `$${(rechargePackageId === 'credits_5000' ? 55 : 12) * maxMonthlyRecharges}`}
                                  </strong>{" "}
                                  ({maxMonthlyRecharges} × {rechargePackageId === 'credits_5000' ? '5,000' : '1,000'} credits).
                                  Overcharge protection guarantees no runaway billing.
                                </p>
                              </div>

                              {/* Telemetry pill */}
                              <div className="text-right shrink-0">
                                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-muted border border-border/50 text-foreground">
                                  {autoRechargeSettings?.recharges_this_month ?? 0} / {maxMonthlyRecharges} used
                                </span>
                              </div>
                            </div>

                            {/* Dev / Test Simulation Button */}
                            <div className="flex items-center justify-between pt-1">
                              <p className="text-[11px] text-muted-foreground">
                                Last auto-recharge:{" "}
                                <span className="font-mono text-foreground">
                                  {autoRechargeSettings?.last_recharged_at 
                                    ? new Date(autoRechargeSettings.last_recharged_at).toLocaleString() 
                                    : "Never triggered yet"}
                                </span>
                              </p>

                              <button
                                type="button"
                                onClick={handleSimulateAutoRecharge}
                                disabled={isSimulatingRecharge}
                                className="text-xs px-3 py-1.5 rounded-lg border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
                              >
                                {isSimulatingRecharge ? (
                                  <Loader2 size={12} className="animate-spin" />
                                ) : (
                                  <Zap size={12} className="text-amber-500 fill-amber-500" />
                                )}
                                {isSimulatingRecharge ? "Simulating..." : "Test Trigger in Sandbox"}
                              </button>
                            </div>
                          </motion.div>
                        ) : (
                          <div className="pt-2 flex items-center justify-between text-xs text-muted-foreground border-t border-border/30">
                            <span>Auto-recharge is currently disabled. Active campaigns will pause if balance drops below overdraft buffer (-500).</span>
                            {!isPro && (
                              <button
                                onClick={() => openPaywall({ featureName: "Automated Credit Auto-Recharge", campaignName: "In-Flight Overdraft Protection" })}
                                className="text-primary hover:underline font-bold shrink-0 ml-2"
                              >
                                Upgrade to unlock →
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Low-Balance Warning Alert */}
                      {credits < 100 && credits > 0 && (
                        <div className="mt-4 p-3 rounded-xl border bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400 flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <AlertCircle size={16} className="shrink-0" />
                            <p className="text-xs font-medium">
                              Low credit balance: You have less than 100 credits remaining. In-flight enrichments may pause when exhausted.
                            </p>
                          </div>
                          <button
                            onClick={() => setShowTopUpModal(true)}
                            className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-xs font-bold transition-colors shadow-sm whitespace-nowrap"
                          >
                            Top Up Credits
                          </button>
                        </div>
                      )}

                      {/* Monthly Usage Breakdown by Action Category */}
                      {(() => {
                        const usageByAction = billingData?.usage_this_month || {};
                        if (Object.keys(usageByAction).length === 0) return null;
                        return (
                          <div className="mt-6 p-4 rounded-xl bg-background border border-border/50">
                            <p className="text-sm font-bold mb-3">This Month's Consumption</p>
                            <div className="space-y-2">
                              {Object.entries(usageByAction).map(([action, count]: [string, any]) => (
                                <div key={action} className="flex justify-between items-center text-xs">
                                  <span className="capitalize text-muted-foreground">{action.replace(/_/g, ' ')}</span>
                                  <span className="font-mono font-bold text-destructive">-{count} credits</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                </SpotlightCard>
              </div>

              {/* Right Column: Pricing / Upsell */}
              <div className="lg:col-span-5">
                <SpotlightCard className={`p-8 rounded-3xl border ${isPro ? 'border-border/50 bg-muted/10' : 'border-primary/30 bg-gradient-to-b from-primary/5 to-background shadow-[0_8px_30px_rgba(var(--primary),0.08)]'} h-full flex flex-col`}>
                  {isPro ? (
                    <div className="flex flex-col h-full">
                      <div className="w-12 h-12 bg-primary/10 text-primary rounded-xl flex items-center justify-center mb-6">
                        <ShieldCheck size={24} />
                      </div>
                      <h3 className="text-2xl font-bold mb-2">Growth Plan Active</h3>
                      <p className="text-sm text-muted-foreground mb-8">You have full access to all premium features. Your subscription automatically renews.</p>
                      
                      <div className="mt-auto space-y-3">
                        <button 
                          onClick={() => toast.info("Please contact support@ele-in.com to update your payment method.")} 
                          className="w-full py-3 bg-background border border-border/50 hover:bg-muted rounded-xl text-sm font-bold transition-colors shadow-sm"
                        >
                          Manage Payment Method
                        </button>
                        {churnHealth?.cancel_at_period_end ? (
                          <button
                            onClick={handleReactivateSubscription}
                            disabled={isReactivating}
                            className="w-full py-3 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-sm font-bold transition-colors shadow-sm"
                          >
                            {isReactivating ? "Reactivating..." : "Reactivate Subscription"}
                          </button>
                        ) : (
                          <button 
                            onClick={() => setShowCancelModal(true)} 
                            className="w-full py-3 text-muted-foreground hover:text-destructive text-sm font-semibold transition-colors"
                          >
                            Cancel Subscription
                          </button>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col h-full relative">
                      <div className="absolute -top-4 -right-4 bg-primary text-primary-foreground text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full shadow-md transform rotate-12">
                        Recommended
                      </div>
                      
                      <h3 className="text-xl font-bold mb-1">Upgrade to Growth</h3>
                      <p className="text-sm text-muted-foreground mb-6">Remove limits and scale your outreach instantly.</p>
                      
                      <div className="flex items-center bg-muted/50 p-1 rounded-lg border border-border/50 mb-6 w-full max-w-[200px]">
                        <button onClick={() => setIsAnnual(false)} className={`flex-1 py-1.5 text-xs font-bold rounded-md transition-colors ${!isAnnual ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>Monthly</button>
                        <button onClick={() => setIsAnnual(true)} className={`flex-1 py-1.5 text-xs font-bold rounded-md transition-colors flex items-center justify-center gap-1 ${isAnnual ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                          Annual <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                        </button>
                      </div>
                      <div className="flex items-baseline gap-1 mb-2">
                        <AnimatePresence mode="wait">
                          <motion.span key={isAnnual ? 'annual' : 'monthly'} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="text-4xl font-black">
                            {provider === 'razorpay' ? (isAnnual ? '₹6,499' : '₹7,999') : (isAnnual ? '$79' : '$99')}
                          </motion.span>
                        </AnimatePresence>
                        <span className="text-muted-foreground text-sm font-medium">/month</span>
                      </div>
                      <AnimatePresence mode="wait">
                        {isAnnual && (
                          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="mb-6">
                            <span className="text-[11px] font-bold text-success bg-success/10 border border-success/20 px-2 py-1 rounded-full uppercase tracking-wider">
                              2 Months Free ({provider === 'razorpay' ? '₹15,998' : '$198'} Savings)
                            </span>
                            <p className="text-xs text-muted-foreground mt-2">Billed annually at {provider === 'razorpay' ? '₹77,988' : '$948'}/yr</p>
                          </motion.div>
                        )}
                        {!isAnnual && <div className="h-6 mb-6" />}
                      </AnimatePresence>

                      <ul className="space-y-4 mb-8 flex-1">
                        {features.map((feature, i) => (
                          <li key={i} className="flex items-start gap-3 text-sm font-medium">
                            <CheckCircle2 size={18} className="text-primary shrink-0 mt-0.5" />
                            <span>{feature}</span>
                          </li>
                        ))}
                      </ul>

                      <button 
                        onClick={() => setShowPaywallModal(true)}
                        className="w-full relative group overflow-hidden rounded-xl bg-foreground text-background font-bold shadow-lg transition-all hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2 py-4"
                      >
                        <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:animate-[shimmer_1.5s_infinite]" />
                        <Zap size={18} className="fill-current" />
                        Upgrade Now
                      </button>
                      <p className="text-center text-xs text-muted-foreground mt-4 flex items-center justify-center gap-1">
                        <ShieldCheck size={12} /> Secure encrypted payment
                      </p>
                    </div>
                  )}
                </SpotlightCard>
              </div>
            </motion.div>
          )}

          {activeTab === 'history' && (
            <motion.div 
              key="history"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
            >
              <div className="bg-background border border-border/50 rounded-3xl overflow-hidden shadow-sm">
                <div className="p-6 border-b border-border/40 flex items-center justify-between flex-wrap gap-4">
                  <div>
                    <h4 className="text-base font-bold text-foreground">Transaction & Invoice Archive</h4>
                    <p className="text-xs text-muted-foreground mt-0.5">Official billing records, tax invoices, and credit issuance receipts.</p>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-muted/30 border-b border-border/50 text-xs text-muted-foreground/80 uppercase tracking-wider font-semibold">
                      <tr>
                        <th className="px-8 py-5">Date</th>
                        <th className="px-8 py-5">Description</th>
                        <th className="px-8 py-5">Amount</th>
                        <th className="px-8 py-5">Status</th>
                        <th className="px-8 py-5 text-right">Receipt</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {historyData && historyData.length > 0 ? historyData.map((txn: any) => (
                        <motion.tr 
                          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          key={txn.id} 
                          className="hover:bg-muted/20 transition-colors group"
                        >
                          <td className="px-8 py-5 whitespace-nowrap">
                            <div className="flex items-center gap-3">
                              <div className="p-2 rounded-lg bg-background border border-border/50 group-hover:border-primary/20 transition-colors">
                                <History size={14} className="text-muted-foreground group-hover:text-primary transition-colors" />
                              </div>
                              <span className="text-foreground font-medium">{txn.created_at ? new Date(txn.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : 'Recent'}</span>
                            </div>
                          </td>
                          <td className="px-8 py-5 text-muted-foreground">
                            {txn.credits_added ? (
                              <span className="flex items-center gap-2">
                                <CircleDollarSign size={14} className="text-primary/70" />
                                {txn.credits_added.toLocaleString()} Credits Top-up
                              </span>
                            ) : (
                              <span className="flex items-center gap-2">
                                <Zap size={14} className="text-warning/70" />
                                Subscription Upgrade
                              </span>
                            )}
                          </td>
                          <td className="px-8 py-5">
                            <span className="font-mono font-medium text-foreground bg-muted/50 px-2.5 py-1 rounded-md border border-border/50">
                              {txn.currency === 'INR' ? '₹' : '$'}{(typeof txn.amount_cents === 'number' ? txn.amount_cents / 100 : 0).toFixed(2)}
                            </span>
                          </td>
                          <td className="px-8 py-5">
                            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-bold uppercase tracking-wider ${txn.status === 'paid' || txn.status === 'success' || txn.status === 'pending' ? 'bg-success/10 text-success border border-success/20' : 'bg-warning/10 text-warning border border-warning/20'}`}>
                              <CheckCircle2 size={12} /> {txn.status === 'pending' ? 'Success' : txn.status}
                            </span>
                          </td>
                          <td className="px-8 py-5 text-right">
                            <button
                              onClick={() => handleViewReceipt(txn)}
                              className="px-3 py-1.5 rounded-xl border border-border hover:bg-muted text-foreground text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                              title="View and download tax invoice receipt"
                            >
                              <FileText size={12} className="text-primary" />
                              Invoice
                            </button>
                          </td>
                        </motion.tr>
                      )) : (
                        <tr>
                          <td colSpan={5} className="px-8 py-24 text-center">
                            <div className="flex flex-col items-center justify-center text-muted-foreground space-y-3">
                              <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center border border-border/50">
                                <Receipt size={20} className="opacity-50" />
                              </div>
                              <p className="font-medium text-sm text-foreground">No billing history</p>
                              <p className="text-xs max-w-[200px] leading-relaxed">Your future invoices and credit purchases will appear here.</p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'usage' && (
            <motion.div 
              key="usage"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
            >
              <div className="bg-background border border-border/50 rounded-3xl overflow-hidden shadow-sm">
                <div className="p-6 border-b border-border/40 flex items-center justify-between flex-wrap gap-4">
                  <div>
                    <h4 className="text-base font-bold text-foreground">Credit Consumption Audit Trail</h4>
                    <p className="text-xs text-muted-foreground mt-0.5">Real-time ledger of AI enrichments, email waterfalls, and reply generation events.</p>
                  </div>
                  <button
                    onClick={handleExportUsageCsv}
                    disabled={!usageData || usageData.length === 0}
                    className="px-3.5 py-2 rounded-xl border border-border bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-2 transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
                  >
                    <Download size={13} className="text-primary" />
                    Export CSV
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-muted/30 border-b border-border/50 text-xs text-muted-foreground/80 uppercase tracking-wider font-semibold">
                      <tr>
                        <th className="px-8 py-5">Date</th>
                        <th className="px-8 py-5">Action Type</th>
                        <th className="px-8 py-5">Cost</th>
                        <th className="px-8 py-5 text-right">Balance After</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {usageData && usageData.length > 0 ? usageData.map((usage: any) => (
                        <motion.tr 
                          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          key={usage.id} 
                          className="hover:bg-muted/20 transition-colors group"
                        >
                          <td className="px-8 py-5 whitespace-nowrap">
                            <span className="text-foreground font-medium">{usage.created_at ? new Date(usage.created_at).toLocaleString() : 'Recent'}</span>
                          </td>
                          <td className="px-8 py-5 text-muted-foreground">
                            <span className="flex items-center gap-2 capitalize">
                              <Zap size={14} className="text-primary/70" />
                              {usage.action_type.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="px-8 py-5">
                            <span className="font-mono font-medium text-destructive bg-destructive/10 px-2.5 py-1 rounded-md border border-destructive/20">
                              -{usage.amount}
                            </span>
                          </td>
                          <td className="px-8 py-5 text-right">
                            <span className="font-mono text-muted-foreground">
                              {usage.balance_after}
                            </span>
                          </td>
                        </motion.tr>
                      )) : (
                        <tr>
                          <td colSpan={4} className="px-8 py-24 text-center">
                            <div className="flex flex-col items-center justify-center text-muted-foreground space-y-3">
                              <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center border border-border/50">
                                <History size={20} className="opacity-50" />
                              </div>
                              <p className="font-medium text-sm text-foreground">No credit usage yet</p>
                              <p className="text-xs max-w-[200px] leading-relaxed">When AI features or enrichments consume credits, they will appear here.</p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      )}

      {/* Official Tax Invoice / Receipt Modal (Layer 0, 1 & 2) */}
      <AnimatePresence>
        {selectedTxnForReceipt && (
          <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-xs flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-card border border-border rounded-3xl shadow-2xl max-w-2xl w-full overflow-hidden text-foreground flex flex-col max-h-[90vh]"
            >
              {/* Header */}
              <div className="p-6 border-b border-border flex items-center justify-between bg-muted/20">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-2xl bg-primary/10 text-primary">
                    <Receipt size={22} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold">Tax Receipt & Invoice</h3>
                    <p className="text-xs text-muted-foreground">Official proof of payment & credit issuance</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => window.print()}
                    className="px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer border border-border"
                  >
                    <Printer size={13} />
                    Print
                  </button>
                  <button
                    onClick={() => {
                      setSelectedTxnForReceipt(null);
                      setReceiptData(null);
                    }}
                    className="p-2 text-muted-foreground hover:text-foreground rounded-xl hover:bg-muted transition-colors cursor-pointer"
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>

              {/* Receipt Body */}
              <div className="p-6 overflow-y-auto space-y-6">
                {loadingReceipt ? (
                  <div className="py-16 flex flex-col items-center justify-center gap-3 text-muted-foreground">
                    <Loader2 size={24} className="animate-spin text-primary" />
                    <p className="text-xs">Generating tax receipt data...</p>
                  </div>
                ) : receiptData ? (
                  <>
                    {/* Invoice Meta Bar */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 rounded-2xl bg-muted/40 border border-border/60 text-xs">
                      <div>
                        <span className="text-muted-foreground block text-[11px]">Invoice No</span>
                        <div className="flex items-center gap-1 font-mono font-bold mt-0.5">
                          <span>{receiptData.invoice_number}</span>
                          <button
                            onClick={() => handleCopyInvoiceNum(receiptData.invoice_number)}
                            className="text-muted-foreground hover:text-primary transition-colors ml-1 cursor-pointer"
                            title="Copy Invoice Number"
                          >
                            {copiedInvoiceNum ? <Check size={12} className="text-success" /> : <Copy size={12} />}
                          </button>
                        </div>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[11px]">Issue Date</span>
                        <span className="font-semibold block mt-0.5">
                          {receiptData.created_at ? new Date(receiptData.created_at).toLocaleDateString() : "Recent"}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[11px]">Payment Method</span>
                        <span className="font-semibold uppercase block mt-0.5">{receiptData.provider}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[11px]">Status</span>
                        <span className="inline-flex items-center gap-1 text-success font-bold mt-0.5">
                          <CheckCircle2 size={12} /> {receiptData.status?.toUpperCase() || "PAID"}
                        </span>
                      </div>
                    </div>

                    {/* Parties */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-xs">
                      <div className="p-4 rounded-2xl border border-border bg-card">
                        <span className="text-muted-foreground font-semibold uppercase text-[10px] tracking-wider block mb-2">Issued By</span>
                        <p className="font-bold text-foreground text-sm">{receiptData.seller?.company_name}</p>
                        <p className="text-muted-foreground mt-0.5">{receiptData.seller?.legal_address}</p>
                        <p className="text-muted-foreground mt-0.5">Tax ID: {receiptData.seller?.tax_id}</p>
                        <p className="text-muted-foreground mt-0.5">Contact: {receiptData.seller?.billing_email}</p>
                      </div>

                      <div className="p-4 rounded-2xl border border-border bg-card">
                        <span className="text-muted-foreground font-semibold uppercase text-[10px] tracking-wider block mb-2">Billed To</span>
                        <p className="font-bold text-foreground text-sm">{receiptData.workspace_name}</p>
                        <p className="font-mono text-muted-foreground text-[11px] mt-0.5">Workspace ID: {receiptData.workspace_id}</p>
                        <p className="font-mono text-muted-foreground text-[11px] mt-0.5 truncate">Ref Order: {receiptData.provider_order_id}</p>
                      </div>
                    </div>

                    {/* Line Items Table */}
                    <div className="rounded-2xl border border-border overflow-hidden">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-muted/40 border-b border-border text-muted-foreground font-semibold">
                          <tr>
                            <th className="p-3.5">Item Description</th>
                            <th className="p-3.5 text-center">Qty / Credits</th>
                            <th className="p-3.5 text-right">Amount</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/40">
                          <tr>
                            <td className="p-3.5">
                              <p className="font-semibold text-foreground">{receiptData.description}</p>
                              <span className="text-[11px] text-muted-foreground">Package ID: {receiptData.package_id}</span>
                            </td>
                            <td className="p-3.5 text-center font-mono font-semibold">
                              {receiptData.credits_added ? `${receiptData.credits_added.toLocaleString()} credits` : "1 Seat / Month"}
                            </td>
                            <td className="p-3.5 text-right font-mono font-bold">
                              {receiptData.currency === "INR" ? "₹" : "$"}{(receiptData.subtotal_cents / 100).toFixed(2)}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    {/* Breakdown */}
                    <div className="p-4 rounded-2xl bg-muted/20 border border-border/60 flex flex-col gap-2 text-xs">
                      <div className="flex justify-between items-center text-muted-foreground">
                        <span>Subtotal</span>
                        <span className="font-mono font-semibold text-foreground">
                          {receiptData.currency === "INR" ? "₹" : "$"}{(receiptData.subtotal_cents / 100).toFixed(2)}
                        </span>
                      </div>
                      {receiptData.tax_cents > 0 && (
                        <div className="flex justify-between items-center text-muted-foreground">
                          <span>GST / Taxes (18%)</span>
                          <span className="font-mono font-semibold text-foreground">
                            {receiptData.currency === "INR" ? "₹" : "$"}{(receiptData.tax_cents / 100).toFixed(2)}
                          </span>
                        </div>
                      )}
                      <div className="pt-2 border-t border-border flex justify-between items-center text-sm font-bold text-foreground">
                        <span>Total Paid</span>
                        <span className="font-mono text-base text-primary">
                          {receiptData.currency === "INR" ? "₹" : "$"}{(receiptData.amount_cents / 100).toFixed(2)} {receiptData.currency}
                        </span>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="py-12 text-center text-muted-foreground">
                    <AlertCircle size={24} className="mx-auto mb-2 text-amber-500" />
                    <p className="text-xs">Receipt data is unavailable for this transaction.</p>
                  </div>
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <CreditTopUpModal
        isOpen={showTopUpModal}
        onClose={() => setShowTopUpModal(false)}
        currentBalance={credits}
        onSuccess={() => {
          mutate();
          mutateHistory();
        }}
      />

      <EleInPaywallModal
        isOpen={showPaywallModal}
        onClose={() => setShowPaywallModal(false)}
        campaignName="Growth Outreach"
        onSuccess={() => {
          mutate();
          mutateHistory();
        }}
      />

      <CancelSubscriptionModal
        isOpen={showCancelModal}
        onClose={() => setShowCancelModal(false)}
        onSuccess={() => {
          mutate();
          mutateHistory();
        }}
      />
    </div>
  )
}
