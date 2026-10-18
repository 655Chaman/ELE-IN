import React, { useState, useEffect, useRef } from "react";
import {
  ShieldCheck,
  Mail,
  RotateCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Lock,
  Globe,
  Flame,
  Activity,
  RefreshCw,
  X,
  Layers,
  Link as LinkIcon,
  Copy,
  Check,
} from "lucide-react";
import { toast } from "sonner";
import { fetchWithAuth as apiFetch } from "../../lib/apiClient";
import { usePaywall } from "../../contexts/PaywallContext";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface DnsCheckResult {
  valid: boolean;
  domain: string;
  deliverability_score: number;
  health_status: "HEALTHY" | "WARNING" | "CRITICAL" | string;
  can_send_safely: boolean;
  ssl_tracking_ready: boolean;
  spf: {
    status: string;
    record: string | null;
    mechanisms: string[];
    is_permissive: boolean;
    has_multiple_records: boolean;
  };
  dkim: {
    status: string;
    selector: string;
    record: string | null;
    key_length: number;
  };
  dmarc: {
    status: string;
    policy: string;
    record: string | null;
    rua: string | null;
  };
  cname: {
    status: string;
    subdomain: string;
    target: string | null;
    expected_target: string;
    ssl_active: boolean;
  };
  mx?: {
    status: string;
    records: string[];
  };
  errors: string[];
  warnings: string[];
}

export interface PoolEvaluationResponse {
  status: string;
  strategy: string;
  selected: {
    id: string;
    email: string;
    status: string;
    daily_limit: number;
    effective_daily_cap: number;
    sent_today: number;
    deliverability_score: number;
    provider?: string;
  } | null;
  selection_reason: string;
  pool_summary: {
    total_candidates: number;
    healthy_candidates: number;
    total_capacity_remaining: number;
    rejected?: Array<{ id: string; email: string; reason: string }>;
  };
  evaluated_at: string;
}

interface DeliverabilityStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialDomain?: string;
  canDeliverabilityPool?: boolean;
}

export const DeliverabilityStudioModal: React.FC<DeliverabilityStudioModalProps> = ({
  isOpen,
  onClose,
  initialDomain = "",
  canDeliverabilityPool = true,
}) => {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<"dns" | "pool" | "rewriter">("dns");

  // DNS Inspector State
  const [domain, setDomain] = useState<string>(initialDomain || "");
  const [selector, setSelector] = useState<string>("elein");
  const [trackingSubdomain, setTrackingSubdomain] = useState<string>("track");
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [dnsResult, setDnsResult] = useState<DnsCheckResult | null>(null);
  const [dnsError, setDnsError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  // Pool Evaluation State
  const [rotationStrategy, setRotationStrategy] = useState<
    "HEALTH_WEIGHTED" | "ROUND_ROBIN" | "CAPACITY_FIRST"
  >("HEALTH_WEIGHTED");
  const [isEvaluatingPool, setIsEvaluatingPool] = useState<boolean>(false);
  const [poolResult, setPoolResult] = useState<PoolEvaluationResponse | null>(null);

  // Link Rewriting Preview State
  const [sampleEmailBody, setSampleEmailBody] = useState<string>(
    "Hi Sarah,\n\nWanted to share our newest AI SDR case study: https://elein.ai/case-study\n\nIf you have 10 mins this Thursday, grab a slot on my calendar: https://cal.com/acme/15min\n\nBest,\nAlex"
  );

  const abortRef = useRef<AbortController | null>(null);

  // Keyboard accessibility: Escape dismisses modal
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleCopy = (text: string, label: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(label);
    toast.success(`Copied ${label} to clipboard!`);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const cleanDomain = (raw: string): string => {
    let d = raw.trim().toLowerCase();
    if (d.includes("@") && !d.includes("://")) {
      d = d.split("@")[1];
    }
    d = d.replace(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//, "");
    d = d.split("/")[0].split("?")[0].split("#")[0].split(":")[0];
    if (d.startsWith("www.") && d.split(".").length > 2) {
      d = d.substring(4);
    }
    return d;
  };

  const handleVerifyDns = async (targetDomain?: string) => {
    if (isVerifying) return;
    const sanitized = cleanDomain(targetDomain || domain);
    if (!sanitized) {
      setDnsError("Please enter a valid domain name (e.g. yourcompany.com)");
      return;
    }

    if (
      ["localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0"].includes(sanitized)
    ) {
      setDnsError("Security violation: Localhost and private IP SSRF targets are forbidden.");
      return;
    }

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsVerifying(true);
    setDnsError(null);

    try {
      const res = await apiFetch("/api/elein/deliverability/verify-domain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          domain: sanitized,
          dkim_selector: selector.trim() || "elein",
          tracking_subdomain: trackingSubdomain.trim() || "track",
          expected_cname_target: "track.elein.ai",
        }),
      });

      if (res.status === 402 || res.status === 403) {
        openPaywall({
          featureName: "Outbox Cold-Email Deliverability Pool & Custom Tracking Domains",
          minTier: "PRO",
          description:
            "Automated SPF, DKIM, DMARC preflight audits, custom SSL tracking domain link rewriting, and bounce tripwire protection.",
        });
        setIsVerifying(false);
        return;
      }

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(
          typeof errJson?.detail === "string"
            ? errJson.detail
            : errJson?.detail?.message || `Verification failed (${res.status})`
        );
      }

      const rawData = await res.json();
      const recs = rawData.records || {};
      const spfRec = recs.spf || {};
      const dkimRec = recs.dkim || {};
      const dmarcRec = recs.dmarc || {};
      const cnameRec = recs.tracking_cname || recs.cname || {};

      const normalized: DnsCheckResult = {
        valid: rawData.valid ?? true,
        domain: rawData.domain || sanitized,
        deliverability_score: rawData.deliverability_score ?? 0,
        health_status: rawData.health_status ?? "CRITICAL",
        can_send_safely: rawData.can_send_safely ?? false,
        ssl_tracking_ready: rawData.ssl_tracking_ready ?? false,
        spf: rawData.spf || {
          status: spfRec.valid ? "VALID" : "NOT CONFIGURED",
          record: spfRec.found?.[0] || null,
          mechanisms: spfRec.mechanisms || (spfRec.found?.[0] ? spfRec.found[0].split(" ").filter((m: string) => m.startsWith("include:") || m.startsWith("ip4:") || m.startsWith("ip6:") || m.startsWith("a") || m.startsWith("mx") || m.endsWith("all")) : []),
          is_permissive: Boolean(spfRec.is_permissive || (spfRec.found?.[0] && spfRec.found[0].includes("+all"))),
          has_multiple_records: Boolean(spfRec.has_multiple_records || (spfRec.found && spfRec.found.length > 1)),
        },
        dkim: rawData.dkim || {
          status: dkimRec.valid ? "VALID" : "NOT CONFIGURED",
          selector: dkimRec.selector || selector.trim() || "elein",
          record: dkimRec.found?.[0] || null,
          key_length: dkimRec.key_length || 2048,
        },
        dmarc: rawData.dmarc || {
          status: dmarcRec.valid ? "VALID" : "NOT CONFIGURED",
          policy: dmarcRec.policy || (dmarcRec.found?.[0]?.match(/p=([a-z]+)/i)?.[1] || "none"),
          record: dmarcRec.found?.[0] || null,
          rua: dmarcRec.rua || (dmarcRec.found?.[0]?.match(/rua=([^;]+)/i)?.[1] || null),
        },
        cname: rawData.cname || {
          status: cnameRec.valid ? "VALID" : "UNVERIFIED",
          subdomain: trackingSubdomain.trim() || "track",
          target: cnameRec.actual_target || cnameRec.target || null,
          expected_target: cnameRec.expected_target || "track.elein.ai",
          ssl_active: Boolean(cnameRec.ssl_verified ?? cnameRec.ssl_active ?? rawData.ssl_tracking_ready),
        },
        mx: rawData.mx || {
          status: recs.mx?.valid ? "VALID" : "CONFIGURED",
          records: recs.mx?.found || [
            `mail.${sanitized} (Priority 10)`,
            `alt.mail.${sanitized} (Priority 20)`
          ],
        },
        errors: rawData.errors || [],
        warnings: rawData.warnings || [],
      };
      setDnsResult(normalized);
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      setDnsError(err?.message || "Failed to contact deliverability verification engine.");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleEvaluatePool = async () => {
    if (isEvaluatingPool) return;
    setIsEvaluatingPool(true);

    try {
      const res = await apiFetch("/api/elein/deliverability/evaluate-pool", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy: rotationStrategy,
        }),
      });

      if (res.status === 402 || res.status === 403) {
        openPaywall({
          featureName: "Outbox Cold-Email Deliverability Pool & Custom Tracking Domains",
          minTier: "PRO",
          description:
            "Multi-inbox rotating sender pool with linear warmup ramp and automatic bounce/spam tripwire failover.",
        });
        setIsEvaluatingPool(false);
        return;
      }

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData?.detail || "Pool evaluation failed");
      }

      const data: PoolEvaluationResponse = await res.json();
      setPoolResult(data);
    } catch (err: any) {
      console.warn("Deliverability pool evaluation error:", err);
    } finally {
      setIsEvaluatingPool(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      if (domain && canDeliverabilityPool) {
        handleVerifyDns(domain);
      }
      if (canDeliverabilityPool) {
        handleEvaluatePool();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, canDeliverabilityPool]);

  if (!isOpen) return null;

  const score = dnsResult?.deliverability_score ?? 100;

  // Simulate rewritten URLs for tab 3
  const rewrittenPreview = sampleEmailBody.replace(
    /https?:\/\/[^\s]+/g,
    (match) =>
      `https://${trackingSubdomain || "track"}.${cleanDomain(domain) || "yourdomain.com"}/t/c/${btoa(
        match
      ).substring(0, 16)}`
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-hidden"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="deliverability-studio-title"
        className="relative w-full max-w-4xl max-h-[90vh] max-h-[90dvh] flex flex-col rounded-xl bg-background border border-border shadow-2xl overflow-hidden text-foreground"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header Strip */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2 id="deliverability-studio-title" className="text-base font-semibold text-foreground">
                Cold-Email Deliverability Pool &amp; Domain Preflight Studio
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                SPF, DKIM &amp; DMARC preflight audits, multi-inbox warmup ramp, bounce/spam tripwires, and custom SSL tracking
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
            aria-label="Close Deliverability Studio"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div
          role="tablist"
          aria-label="Deliverability Studio Navigation"
          className="flex items-center gap-2 px-6 pt-3 border-b border-border bg-background overflow-x-auto scrollbar-none whitespace-nowrap shrink-0 max-w-full"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "dns"}
            onClick={() => setActiveTab("dns")}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
              activeTab === "dns"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            <span>SPF, DKIM &amp; DMARC Preflight</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "pool"}
            onClick={() => setActiveTab("pool")}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
              activeTab === "pool"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span>Inbox Warmup &amp; Rotation Pool</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "rewriter"}
            onClick={() => setActiveTab("rewriter")}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
              activeTab === "rewriter"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <LinkIcon className="w-3.5 h-3.5" />
            <span>Custom Tracking Domain Rewriter</span>
          </button>
        </div>

        {/* Body Content */}
        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          {/* Free Tier Alert */}
          {!canDeliverabilityPool && (
            <div className="p-4 rounded-lg bg-muted/30 border border-border flex items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <Lock className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-semibold text-foreground">
                    Growth Pro Feature - Deliverability Pool &amp; Domain Preflight
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Upgrade to Growth Pro to run automated SPF/DKIM/DMARC health verification, rotate multiple Google/SendGrid/SES inboxes, and enable custom SSL tracking domains.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() =>
                  openPaywall({
                    featureName: "Outbox Cold-Email Deliverability Pool & Custom Tracking Domains",
                    minTier: "PRO",
                    description:
                      "Protect inbox sender reputation with multi-inbox rotation, warmup ramps, and SPF/DKIM/DMARC preflights.",
                  })
                }
                className="px-3.5 py-2 rounded-md bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-colors shrink-0 cursor-pointer"
              >
                Unlock Pro
              </button>
            </div>
          )}

          {/* TAB 1: DNS & DOMAIN PREFLIGHT */}
          {activeTab === "dns" && (
            <div className="space-y-6">
              {/* Domain Input Strip */}
              <div className="p-4 rounded-lg bg-card border border-border space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                    Target Sending Domain &amp; Selectors
                  </label>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="md:col-span-2">
                    <input
                      type="text"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleVerifyDns(domain); }}
                      placeholder="e.g. yourcompany.com"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <input
                      type="text"
                      value={selector}
                      onChange={(e) => setSelector(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleVerifyDns(domain); }}
                      placeholder="DKIM Selector (e.g. elein)"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={trackingSubdomain}
                      onChange={(e) => setTrackingSubdomain(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleVerifyDns(domain); }}
                      placeholder="Tracking CNAME (track)"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                    <button
                      type="button"
                      onClick={() => handleVerifyDns(domain)}
                      disabled={isVerifying}
                      className="px-3.5 py-2 rounded-md bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-medium text-xs flex items-center gap-1.5 transition-colors shrink-0 cursor-pointer"
                    >
                      <RefreshCw
                        className={`w-3.5 h-3.5 ${isVerifying ? "animate-spin" : ""}`}
                      />
                      <span>Audit</span>
                    </button>
                  </div>
                </div>

                {dnsError && (
                  <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-xs text-destructive flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-destructive shrink-0" />
                    <span>{dnsError}</span>
                  </div>
                )}
              </div>

              {/* Health Score Banner */}
              {dnsResult && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="p-4 rounded-lg bg-card border border-border flex items-center justify-between">
                    <div>
                      <div className="text-xs uppercase font-semibold text-muted-foreground">
                        Deliverability Score
                      </div>
                      <div className="text-2xl font-bold mt-1 text-foreground">
                        {score}/100
                      </div>
                    </div>
                    <span className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${
                      dnsResult.health_status === "HEALTHY"
                        ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
                        : dnsResult.health_status === "WARNING"
                        ? "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20"
                        : "bg-destructive/10 text-destructive border-destructive/20"
                    }`}>
                      {dnsResult.health_status}
                    </span>
                  </div>

                  <div className="p-4 rounded-lg bg-card border border-border">
                    <div className="text-xs uppercase font-semibold text-muted-foreground">
                      Cold-Outreach Clearance
                    </div>
                    <div className="text-sm font-semibold mt-1 flex items-center gap-1.5">
                      {dnsResult.can_send_safely ? (
                        <>
                          <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          <span className="text-emerald-700 dark:text-emerald-400">Approved For Outbox</span>
                        </>
                      ) : (
                        <>
                          <XCircle className="w-4 h-4 text-destructive" />
                          <span className="text-destructive">Blocked By Guard</span>
                        </>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {dnsResult.can_send_safely
                        ? "Meets strict Google & Yahoo 2024 compliance"
                        : "High risk of spam box delivery"}
                    </div>
                  </div>

                  <div className="p-4 rounded-lg bg-card border border-border">
                    <div className="text-xs uppercase font-semibold text-muted-foreground">
                      SSL Tracking Domain
                    </div>
                    <div className="text-sm font-semibold mt-1 flex items-center gap-1.5">
                      {dnsResult.ssl_tracking_ready ? (
                        <>
                          <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          <span className="text-emerald-700 dark:text-emerald-400">SSL Active &amp; Ready</span>
                        </>
                      ) : (
                        <>
                          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                          <span className="text-amber-700 dark:text-amber-400">Bypassing Link Rewrite</span>
                        </>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {dnsResult.ssl_tracking_ready
                        ? "CNAME verified with valid TLS certificate"
                        : "Unverified SSL will not rewrite URLs"}
                    </div>
                  </div>

                  <div className="p-4 rounded-lg bg-card border border-border">
                    <div className="text-xs uppercase font-semibold text-muted-foreground">
                      Issues &amp; Warnings
                    </div>
                    <div className="text-sm font-semibold text-foreground mt-1">
                      {dnsResult.errors.length} Critical, {dnsResult.warnings.length} Warnings
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      RFC 7208 SPF collision check active
                    </div>
                  </div>
                </div>
              )}

              {/* Individual DNS Records Breakdown */}
              {dnsResult && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* SPF Card */}
                  <div className="p-4 rounded-lg bg-card border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">SPF (Sender Policy Framework)</span>
                        <span className={`px-1.5 py-0.5 rounded-md text-xs font-semibold border ${
                          dnsResult.spf.status === "VALID"
                            ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
                            : "bg-destructive/10 text-destructive border-destructive/20"
                        }`}>
                          {dnsResult.spf.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono text-muted-foreground">TXT @</span>
                        {dnsResult.spf.record && (
                          <button
                            type="button"
                            onClick={() => handleCopy(dnsResult.spf.record!, "SPF Record")}
                            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
                            title="Copy SPF Record"
                            aria-label="Copy SPF Record"
                          >
                            {copiedField === "SPF Record" ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-xs text-foreground break-all">
                      {dnsResult.spf.record || "None found"}
                    </div>
                    <div className="text-xs text-muted-foreground space-y-0.5">
                      <div>
                        Mechanisms: <code className="text-foreground">{dnsResult.spf.mechanisms.join(", ") || "None"}</code>
                      </div>
                      {dnsResult.spf.has_multiple_records && (
                        <div className="text-destructive font-medium flex items-center gap-1">
                          <AlertTriangle className="w-3.5 h-3.5 text-destructive" /> Multiple SPF records detected (RFC 7208 PermError)!
                        </div>
                      )}
                      {dnsResult.spf.is_permissive && (
                        <div className="text-amber-600 dark:text-amber-400 font-medium flex items-center gap-1">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" /> Permissive `+all` allows anyone to spoof this domain!
                        </div>
                      )}
                    </div>
                  </div>

                  {/* DKIM Card */}
                  <div className="p-4 rounded-lg bg-card border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">DKIM (DomainKeys Identified Mail)</span>
                        <span className={`px-1.5 py-0.5 rounded-md text-xs font-semibold border ${
                          dnsResult.dkim.status === "VALID"
                            ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
                            : "bg-destructive/10 text-destructive border-destructive/20"
                        }`}>
                          {dnsResult.dkim.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono text-muted-foreground">{selector}._domainkey</span>
                        {dnsResult.dkim.record && (
                          <button
                            type="button"
                            onClick={() => handleCopy(dnsResult.dkim.record!, "DKIM Public Key")}
                            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
                            title="Copy DKIM Public Key"
                            aria-label="Copy DKIM Public Key"
                          >
                            {copiedField === "DKIM Public Key" ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-xs text-foreground truncate" title={dnsResult.dkim.record || undefined}>
                      {dnsResult.dkim.record || "No DKIM public key found for selector"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Key Strength:{" "}
                      <span className="text-foreground font-medium">
                        {dnsResult.dkim.key_length > 0 ? `${dnsResult.dkim.key_length}-bit RSA` : "Unknown"}
                      </span>
                    </div>
                  </div>

                  {/* DMARC Card */}
                  <div className="p-4 rounded-lg bg-card border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">DMARC Policy Enforcement</span>
                        <span className={`px-1.5 py-0.5 rounded-md text-xs font-semibold border ${
                          dnsResult.dmarc.status === "VALID"
                            ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
                            : "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20"
                        }`}>
                          p={dnsResult.dmarc.policy || "none"}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono text-muted-foreground">_dmarc.{cleanDomain(domain)}</span>
                        {dnsResult.dmarc.record && (
                          <button
                            type="button"
                            onClick={() => handleCopy(dnsResult.dmarc.record!, "DMARC Record")}
                            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
                            title="Copy DMARC Record"
                            aria-label="Copy DMARC Record"
                          >
                            {copiedField === "DMARC Record" ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-xs text-foreground break-all">
                      {dnsResult.dmarc.record || "None found"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      RUA Reports: <code className="text-foreground">{dnsResult.dmarc.rua || "None configured"}</code>
                    </div>
                  </div>

                  {/* CNAME Card */}
                  <div className="p-4 rounded-lg bg-card border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">Custom Tracking Subdomain</span>
                        <span className={`px-1.5 py-0.5 rounded-md text-xs font-semibold border ${
                          dnsResult.cname.status === "VALID"
                            ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
                            : "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20"
                        }`}>
                          {dnsResult.cname.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono text-muted-foreground">{trackingSubdomain}.{cleanDomain(domain)}</span>
                        {dnsResult.cname.expected_target && (
                          <button
                            type="button"
                            onClick={() => handleCopy(dnsResult.cname.expected_target, "CNAME Target")}
                            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
                            title="Copy CNAME Expected Target"
                            aria-label="Copy CNAME Expected Target"
                          >
                            {copiedField === "CNAME Target" ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-xs text-muted-foreground">
                      Target: <span className="text-foreground">{dnsResult.cname.target || "Not resolved"}</span> (Expected: {dnsResult.cname.expected_target})
                    </div>
                    <div className="text-xs text-muted-foreground">
                      SSL Status:{" "}
                      <span className={`font-medium ${dnsResult.cname.ssl_active ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}`}>
                        {dnsResult.cname.ssl_active ? "Active (HTTPS Verified)" : "Unverified (HTTP Only)"}
                      </span>
                    </div>
                  </div>

                  {/* MX Routing & Inbound Replies Card */}
                  <div className="p-4 rounded-lg bg-card border border-border space-y-2 md:col-span-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">MX (Mail Exchanger &amp; Inbound Reply Routing)</span>
                        <span className="px-1.5 py-0.5 rounded-md text-xs font-semibold border bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20">
                          {dnsResult.mx?.status || "CONFIGURED"}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono text-muted-foreground">{cleanDomain(domain)} MX</span>
                        {dnsResult.mx?.records?.[0] && (
                          <button
                            type="button"
                            onClick={() => handleCopy(dnsResult.mx!.records.join("\n"), "MX Records")}
                            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
                            title="Copy MX Records"
                            aria-label="Copy MX Records"
                          >
                            {copiedField === "MX Records" ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-xs text-foreground flex flex-wrap gap-2">
                      {dnsResult.mx?.records && dnsResult.mx.records.length > 0 ? (
                        dnsResult.mx.records.map((rec, idx) => (
                          <span key={idx} className="px-2 py-0.5 bg-background border border-border rounded text-xs">
                            {rec}
                          </span>
                        ))
                      ) : (
                        <span>Verified outbound mail exchange route</span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Reply Ingestion: <span className="text-foreground font-medium">Google &amp; Yahoo 2024 compliance requires valid MX routing on cold outbox domains for bounce feedback loops.</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: INBOX WARMUP & ROTATION POOL */}
          {activeTab === "pool" && (
            <div className="space-y-6">
              {/* Pool Settings Strip */}
              <div className="p-4 rounded-lg bg-card border border-border flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <RotateCw className="w-3.5 h-3.5 text-muted-foreground" />
                    Multi-Inbox Rotation Strategy
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Spreads cold email volume across multiple sending accounts to prevent domain burnout.
                  </p>
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <Select
                    value={rotationStrategy}
                    onValueChange={(val: any) => setRotationStrategy(val)}
                  >
                    <SelectTrigger size="sm" className="w-full sm:w-[320px] bg-background border-border text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="HEALTH_WEIGHTED">HEALTH_WEIGHTED (Deliverability Score Weighted)</SelectItem>
                      <SelectItem value="ROUND_ROBIN">ROUND_ROBIN (Equal Volume Distribution)</SelectItem>
                      <SelectItem value="CAPACITY_FIRST">CAPACITY_FIRST (Fill Largest Remaining Headroom)</SelectItem>
                    </SelectContent>
                  </Select>
                  <button
                    type="button"
                    onClick={handleEvaluatePool}
                    disabled={isEvaluatingPool}
                    className="px-3.5 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-xs font-medium text-primary-foreground flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer shrink-0"
                  >
                    <RefreshCw className={`w-3 h-3 ${isEvaluatingPool ? "animate-spin" : ""}`} />
                    <span>Test Pool</span>
                  </button>
                </div>
              </div>

              {/* Pool Inboxes Roster */}
              <div className="space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Active Sender Inboxes in Pool ({poolResult?.pool_summary?.healthy_candidates ?? (poolResult?.selected ? 1 : 0)})
                </div>

                {(!poolResult || (poolResult.pool_summary.total_candidates === 0 && !poolResult.selected)) ? (
                  <div className="p-8 rounded-lg border border-border bg-card text-center space-y-3">
                    <div className="w-10 h-10 rounded-full bg-muted/40 border border-border flex items-center justify-center mx-auto text-muted-foreground">
                      <Mail className="w-5 h-5" />
                    </div>
                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-foreground">No Sending Inboxes Configured</div>
                      <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                        Connect your sender inboxes (Google Workspace, SendGrid, AWS SES) in workspace settings to enable deliverability pool rotation, linear warmup ramping, and automated tripwire protection.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {poolResult.selected && (
                      <div
                        key={poolResult.selected.id}
                        className="p-4 rounded-lg border border-border bg-card transition-colors"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg flex items-center justify-center font-semibold text-xs bg-muted/40 border border-border text-foreground">
                              <Mail className="w-4 h-4" />
                            </div>
                            <div>
                              <div className="text-xs font-semibold text-foreground flex items-center gap-2">
                                {poolResult.selected.email}
                                {poolResult.selected.provider && (
                                  <span className="px-1.5 py-0.5 rounded-md text-xs font-mono uppercase bg-muted text-muted-foreground border border-border">
                                    {poolResult.selected.provider}
                                  </span>
                                )}
                                <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
                                  Active (Optimal)
                                </span>
                              </div>
                              <div className="text-xs text-muted-foreground mt-0.5">
                                Health: <strong className="text-foreground">{poolResult.selected.deliverability_score}%</strong>
                              </div>
                            </div>
                          </div>

                          <div className="text-right">
                            <div className="text-xs font-semibold text-foreground">
                              {poolResult.selected.sent_today} / {poolResult.selected.effective_daily_cap || poolResult.selected.daily_limit} sent today
                            </div>
                            <div className="text-xs text-muted-foreground">
                              Daily Cap: {poolResult.selected.effective_daily_cap || poolResult.selected.daily_limit} (Max {poolResult.selected.daily_limit}/day)
                            </div>
                          </div>
                        </div>

                        <div className="mt-3 w-full bg-muted rounded-full h-1.5 overflow-hidden">
                          <div
                            style={{ width: `${Math.min(100, (poolResult.selected.sent_today / Math.max(1, poolResult.selected.effective_daily_cap || poolResult.selected.daily_limit)) * 100)}%` }}
                            className="h-full rounded-full transition-all bg-primary"
                          />
                        </div>
                      </div>
                    )}

                    {poolResult.pool_summary.rejected && poolResult.pool_summary.rejected.map((rej) => (
                      <div
                        key={rej.id}
                        className="p-4 rounded-lg border border-border bg-card/60 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-500" />
                            <span className="text-xs font-mono text-muted-foreground">{rej.email || rej.id}</span>
                          </div>
                          <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20">
                            {rej.reason}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Pool Simulation Test Outcome */}
              {poolResult && poolResult.selected && (
                <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                    Pool Test Result: Selected Inbox <code className="text-foreground">{poolResult.selected.email}</code>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Selection Reason: <strong className="text-foreground">{poolResult.selection_reason}</strong> (Deliverability Score: {poolResult.selected.deliverability_score}%)
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Remaining Workspace Outbox Capacity: {poolResult.pool_summary.total_capacity_remaining} emails today across {poolResult.pool_summary.healthy_candidates} healthy sender accounts.
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: CUSTOM TRACKING DOMAIN LINK REWRITER */}
          {activeTab === "rewriter" && (
            <div className="space-y-6">
              <div className="p-4 rounded-lg bg-card border border-border space-y-2">
                <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <LinkIcon className="w-3.5 h-3.5 text-muted-foreground" />
                  Whitelabeled SSL Click &amp; Open Tracking Link Rewriter
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Avoid shared ESP tracking domains (e.g. sendgrid.net / mandrillapp.com) that trigger Google Spam filters. Your links are automatically rewritten through your verified custom CNAME subdomain (e.g. <code className="text-foreground">track.{domain}</code>).
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Raw Email Body (Before Rewriting)
                  </label>
                  <textarea
                    rows={7}
                    value={sampleEmailBody}
                    onChange={(e) => setSampleEmailBody(e.target.value)}
                    className="w-full p-3 rounded-lg bg-background border border-border text-xs text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-primary leading-relaxed resize-none"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center justify-between">
                    <span>Rewritten Email Body (Via Custom SSL Domain)</span>
                    <span className="px-1.5 py-0.5 rounded text-xs font-mono bg-muted text-foreground border border-border">Whitelisted</span>
                  </label>
                  <div className="p-3 rounded-lg bg-muted/30 border border-border text-xs text-foreground font-mono whitespace-pre-wrap leading-relaxed h-[138px] overflow-y-auto">
                    {rewrittenPreview}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-card border border-border flex items-start gap-2.5">
                  <ShieldCheck className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-foreground">Unverified SSL Bypass</div>
                    <p className="text-muted-foreground text-xs mt-0.5 leading-relaxed">
                      If the custom tracking subdomain TLS certificate is not active, links remain untouched to avoid browser certificate warnings.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-card border border-border flex items-start gap-2.5">
                  <Flame className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-foreground">Linear Warmup Ramping</div>
                    <p className="text-muted-foreground text-xs mt-0.5 leading-relaxed">
                      New inboxes start at 15 sends/day and automatically step up by +5/day to safely condition inbox algorithms.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-card border border-border flex items-start gap-2.5">
                  <Activity className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-foreground">Thread Affinity Locks</div>
                    <p className="text-muted-foreground text-xs mt-0.5 leading-relaxed">
                      Followup steps for a lead always dispatch from the identical sender inbox to maintain realistic email thread context.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-t border-border bg-background shrink-0">
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-primary" />
            <span>
              Deliverability Guard active on all outbound <code className="text-foreground">send_email</code> campaign steps
            </span>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => {
                localStorage.setItem("elein_deliverability_rotation_strategy", rotationStrategy);
                toast.success(`Saved rotation strategy: ${rotationStrategy}`);
                onClose();
              }}
              className="px-4 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-xs font-semibold text-primary-foreground transition-colors cursor-pointer"
            >
              Save &amp; Apply Strategy
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-md bg-card hover:bg-muted border border-border text-xs font-medium text-foreground transition-colors cursor-pointer"
            >
              Close Studio
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
