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
  Zap,
  Activity,
  ArrowRight,
  RefreshCw,
  X,
  Layers,
  Link as LinkIcon,
  HelpCircle,
  Clock,
  Server,
  TrendingUp,
} from "lucide-react";
import { fetchWithAuth as apiFetch } from "../../lib/apiClient";
import { usePaywall } from "../../contexts/PaywallContext";

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

const DEMO_PRESETS = [
  {
    label: "Google Workspace + SendGrid (Healthy 100%)",
    domain: "acmecorp.com",
    selector: "elein",
    subdomain: "track",
    mock: {
      spf: ["v=spf1 include:_spf.google.com include:sendgrid.net ~all"],
      dkim: ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"],
      dmarc: ["v=DMARC1; p=reject; rua=mailto:dmarc@acmecorp.com"],
      cname: "track.elein.ai",
      ssl_verified: true,
    },
  },
  {
    label: "Permissive DMARC + Missing SSL Warning (72%)",
    domain: "tryhypergrowth.io",
    selector: "default",
    subdomain: "track",
    mock: {
      spf: ["v=spf1 include:sendgrid.net ~all"],
      dkim: ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"],
      dmarc: ["v=DMARC1; p=none; rua=mailto:admin@tryhypergrowth.io"],
      cname: "track.elein.ai",
      ssl_verified: false,
    },
  },
  {
    label: "RFC 7208 Multiple SPF Collision (Critical 28%)",
    domain: "vulnerable-sales.com",
    selector: "elein",
    subdomain: "track",
    mock: {
      spf: [
        "v=spf1 include:_spf.google.com ~all",
        "v=spf1 include:mailgun.org +all",
      ],
      dkim: [],
      dmarc: ["v=DMARC1; p=none;"],
      cname: "unconfigured.dns.provider",
      ssl_verified: false,
    },
  },
];

const SAMPLE_INBOX_POOL = [
  {
    id: "inb-alpha",
    email: "sarah@outreach.acmecorp.com",
    provider: "google_workspace",
    status: "ACTIVE",
    daily_limit: 60,
    warmup_days_active: 8,
    warmup_start_limit: 15,
    sent_today: 18,
    deliverability_score: 98,
    bounce_rate: 0.8,
  },
  {
    id: "inb-beta",
    email: "alex@outreach2.acmecorp.com",
    provider: "sendgrid",
    status: "ACTIVE",
    daily_limit: 60,
    warmup_days_active: 14,
    warmup_start_limit: 15,
    sent_today: 34,
    deliverability_score: 94,
    bounce_rate: 1.2,
  },
  {
    id: "inb-gamma",
    email: "jordan@mail.acmecorp.com",
    provider: "ses",
    status: "QUARANTINED",
    daily_limit: 50,
    warmup_days_active: 3,
    warmup_start_limit: 15,
    sent_today: 12,
    deliverability_score: 62,
    bounce_rate: 3.1, // Crossed 2.5% tripwire!
    quarantine_reason: "BOUNCE_RATE_EXCEEDED (3.1% >= 2.5%)",
  },
];

export const DeliverabilityStudioModal: React.FC<DeliverabilityStudioModalProps> = ({
  isOpen,
  onClose,
  initialDomain = "acmecorp.com",
  canDeliverabilityPool = true,
}) => {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<"dns" | "pool" | "rewriter">("dns");

  // DNS Inspector State
  const [domain, setDomain] = useState<string>(initialDomain || "acmecorp.com");
  const [selector, setSelector] = useState<string>("elein");
  const [trackingSubdomain, setTrackingSubdomain] = useState<string>("track");
  const [activeMock, setActiveMock] = useState<any>(DEMO_PRESETS[0].mock);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [dnsResult, setDnsResult] = useState<DnsCheckResult | null>(null);
  const [dnsError, setDnsError] = useState<string | null>(null);

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

  const handleVerifyDns = async (targetDomain?: string, mockOverride?: any) => {
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
          mock_records: mockOverride !== undefined ? mockOverride : activeMock,
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

      const data: DnsCheckResult = await res.json();
      setDnsResult(data);
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
          candidate_inboxes: SAMPLE_INBOX_POOL,
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
      handleVerifyDns(domain, DEMO_PRESETS[0].mock);
      handleEvaluatePool();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const score = dnsResult?.deliverability_score ?? 100;

  // Simulate rewritten URLs for tab 3
  const rewrittenPreview = sampleEmailBody.replace(
    /https?:\/\/[^\s]+/g,
    (match) =>
      `https://${trackingSubdomain || "track"}.${cleanDomain(domain) || "acmecorp.com"}/t/c/${btoa(
        match
      ).substring(0, 16)}`
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl rounded-2xl bg-background border border-border shadow-lg overflow-hidden text-foreground my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header Strip */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-muted/40 border border-border flex items-center justify-center text-foreground">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">
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
            className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 px-6 pt-3 border-b border-border bg-background">
          <button
            type="button"
            onClick={() => setActiveTab("dns")}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === "dns"
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            SPF, DKIM &amp; DMARC Preflight
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("pool")}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === "pool"
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <RotateCw className="w-3.5 h-3.5" />
            Inbox Warmup &amp; Rotation Pool
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("rewriter")}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === "rewriter"
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <LinkIcon className="w-3.5 h-3.5" />
            Custom Tracking Domain Rewriter
          </button>
        </div>

        {/* Body Content */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
          {/* Free Tier Alert */}
          {!canDeliverabilityPool && (
            <div className="p-4 rounded-lg bg-muted/30 border border-border flex items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <Lock className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-semibold text-foreground">
                    Growth Pro Feature - Deliverability Pool &amp; Domain Preflight
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
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
                className="px-3.5 py-2 rounded-md bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-colors shrink-0"
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
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                    Target Sending Domain &amp; Selectors
                  </label>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground">Presets:</span>
                    {DEMO_PRESETS.map((p, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => {
                          setDomain(p.domain);
                          setSelector(p.selector);
                          setTrackingSubdomain(p.subdomain);
                          setActiveMock(p.mock);
                          handleVerifyDns(p.domain, p.mock);
                        }}
                        className="text-[10px] px-2 py-0.5 rounded-md bg-muted/40 hover:bg-muted text-foreground border border-border transition-colors"
                      >
                        {p.label.split(" ")[0]}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="md:col-span-2">
                    <input
                      type="text"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder="e.g. acmecorp.com"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <input
                      type="text"
                      value={selector}
                      onChange={(e) => setSelector(e.target.value)}
                      placeholder="DKIM Selector (e.g. elein)"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={trackingSubdomain}
                      onChange={(e) => setTrackingSubdomain(e.target.value)}
                      placeholder="Tracking CNAME (track)"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                    <button
                      type="button"
                      onClick={() => handleVerifyDns(domain, activeMock)}
                      disabled={isVerifying}
                      className="px-3.5 py-2 rounded-md bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-medium text-xs flex items-center gap-1.5 transition-colors shrink-0"
                    >
                      <RefreshCw
                        className={`w-3.5 h-3.5 ${isVerifying ? "animate-spin" : ""}`}
                      />
                      Audit
                    </button>
                  </div>
                </div>

                {dnsError && (
                  <div className="p-3 rounded-lg bg-muted/30 border border-border text-xs text-foreground flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-muted-foreground shrink-0" />
                    <span>{dnsError}</span>
                  </div>
                )}
              </div>

              {/* Health Score Banner */}
              {dnsResult && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="p-4 rounded-lg bg-card border border-border flex items-center justify-between">
                    <div>
                      <div className="text-[10px] uppercase font-semibold text-muted-foreground">
                        Deliverability Score
                      </div>
                      <div className="text-2xl font-bold mt-1 text-foreground">
                        {score}/100
                      </div>
                    </div>
                    <span className="px-2.5 py-1 rounded-md text-xs font-medium border border-border bg-muted text-foreground">
                      {dnsResult.health_status}
                    </span>
                  </div>

                  <div className="p-4 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase font-semibold text-muted-foreground">
                      Cold-Outreach Clearance
                    </div>
                    <div className="text-sm font-semibold text-foreground mt-1 flex items-center gap-1.5">
                      {dnsResult.can_send_safely ? (
                        <>
                          <CheckCircle2 className="w-4 h-4 text-muted-foreground" />
                          <span>Approved For Outbox</span>
                        </>
                      ) : (
                        <>
                          <XCircle className="w-4 h-4 text-muted-foreground" />
                          <span>Blocked By Guard</span>
                        </>
                      )}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      {dnsResult.can_send_safely
                        ? "Meets strict Google & Yahoo 2024 compliance"
                        : "High risk of spam box delivery"}
                    </div>
                  </div>

                  <div className="p-4 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase font-semibold text-muted-foreground">
                      SSL Tracking Domain
                    </div>
                    <div className="text-sm font-semibold text-foreground mt-1 flex items-center gap-1.5">
                      {dnsResult.ssl_tracking_ready ? (
                        <>
                          <ShieldCheck className="w-4 h-4 text-muted-foreground" />
                          <span>SSL Active &amp; Ready</span>
                        </>
                      ) : (
                        <>
                          <AlertTriangle className="w-4 h-4 text-muted-foreground" />
                          <span>Bypassing Link Rewrite</span>
                        </>
                      )}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      {dnsResult.ssl_tracking_ready
                        ? "CNAME verified with valid TLS certificate"
                        : "Unverified SSL will not rewrite URLs"}
                    </div>
                  </div>

                  <div className="p-4 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase font-semibold text-muted-foreground">
                      Issues &amp; Warnings
                    </div>
                    <div className="text-sm font-semibold text-foreground mt-1">
                      {dnsResult.errors.length} Critical, {dnsResult.warnings.length} Warnings
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
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
                        <span className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-muted text-foreground border border-border">
                          {dnsResult.spf.status}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">TXT @</span>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-[11px] text-foreground break-all">
                      {dnsResult.spf.record || "None found"}
                    </div>
                    <div className="text-[10px] text-muted-foreground space-y-0.5">
                      <div>
                        Mechanisms: <code className="text-foreground">{dnsResult.spf.mechanisms.join(", ") || "None"}</code>
                      </div>
                      {dnsResult.spf.has_multiple_records && (
                        <div className="text-foreground font-medium flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3 text-muted-foreground" /> Multiple SPF records detected (RFC 7208 PermError)!
                        </div>
                      )}
                      {dnsResult.spf.is_permissive && (
                        <div className="text-foreground font-medium flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3 text-muted-foreground" /> Permissive `+all` allows anyone to spoof this domain!
                        </div>
                      )}
                    </div>
                  </div>

                  {/* DKIM Card */}
                  <div className="p-4 rounded-lg bg-card border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">DKIM (DomainKeys Identified Mail)</span>
                        <span className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-muted text-foreground border border-border">
                          {dnsResult.dkim.status}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">{selector}._domainkey</span>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-[11px] text-foreground truncate">
                      {dnsResult.dkim.record || "No DKIM public key found for selector"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
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
                        <span className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-muted text-foreground border border-border">
                          p={dnsResult.dmarc.policy || "none"}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">_dmarc.{domain}</span>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-[11px] text-foreground break-all">
                      {dnsResult.dmarc.record || "None found"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      RUA Reports: <code className="text-foreground">{dnsResult.dmarc.rua || "None configured"}</code>
                    </div>
                  </div>

                  {/* CNAME Card */}
                  <div className="p-4 rounded-lg bg-card border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">Custom Tracking Subdomain</span>
                        <span className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-muted text-foreground border border-border">
                          {dnsResult.cname.status}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">{trackingSubdomain}.{domain}</span>
                    </div>
                    <div className="p-2.5 rounded-md bg-muted/30 border border-border font-mono text-[11px] text-muted-foreground">
                      Target: <span className="text-foreground">{dnsResult.cname.target || "Not resolved"}</span> (Expected: {dnsResult.cname.expected_target})
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      SSL Status:{" "}
                      <span className="text-foreground font-medium">
                        {dnsResult.cname.ssl_active ? "Active (HTTPS Verified)" : "Unverified (HTTP Only)"}
                      </span>
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
                  <p className="text-[11px] text-muted-foreground">
                    Spreads cold email volume across multiple sending accounts to prevent domain burnout.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={rotationStrategy}
                    onChange={(e: any) => setRotationStrategy(e.target.value)}
                    className="px-3 py-1.5 rounded-md bg-background border border-border text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="HEALTH_WEIGHTED">HEALTH_WEIGHTED (Deliverability Score Weighted)</option>
                    <option value="ROUND_ROBIN">ROUND_ROBIN (Equal Volume Distribution)</option>
                    <option value="CAPACITY_FIRST">CAPACITY_FIRST (Fill Largest Remaining Headroom)</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleEvaluatePool}
                    disabled={isEvaluatingPool}
                    className="px-3.5 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-xs font-medium text-primary-foreground flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3 h-3 ${isEvaluatingPool ? "animate-spin" : ""}`} />
                    Test Pool
                  </button>
                </div>
              </div>

              {/* Pool Inboxes Roster */}
              <div className="space-y-3">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Active Sender Inboxes in Pool ({SAMPLE_INBOX_POOL.length})
                </div>
                <div className="space-y-2.5">
                  {SAMPLE_INBOX_POOL.map((inbox) => {
                    const rampCap = inbox.warmup_start_limit + inbox.warmup_days_active * 5;
                    const effectiveCap = Math.min(inbox.daily_limit, rampCap);
                    const isQuarantined = inbox.status === "QUARANTINED";

                    return (
                      <div
                        key={inbox.id}
                        className="p-4 rounded-lg border border-border bg-card transition-colors"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg flex items-center justify-center font-semibold text-xs bg-muted/40 border border-border text-foreground">
                              <Mail className="w-4 h-4" />
                            </div>
                            <div>
                              <div className="text-xs font-semibold text-foreground flex items-center gap-2">
                                {inbox.email}
                                <span className="px-1.5 py-0.5 rounded-md text-[9px] font-mono uppercase bg-muted text-muted-foreground border border-border">
                                  {inbox.provider}
                                </span>
                                {isQuarantined ? (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-muted text-muted-foreground border border-border">
                                    Quarantined (Tripwire Tripped)
                                  </span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-primary/10 text-foreground border border-border">
                                    Active (Day {inbox.warmup_days_active} Warmup)
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-muted-foreground mt-0.5">
                                Health: <strong className="text-foreground">{inbox.deliverability_score}%</strong> - Bounce Rate:{" "}
                                <strong className="text-foreground">
                                  {inbox.bounce_rate}%
                                </strong>{" "}
                                (Tripwire: 2.5%)
                              </div>
                            </div>
                          </div>

                          <div className="text-right">
                            <div className="text-xs font-semibold text-foreground">
                              {inbox.sent_today} / {effectiveCap} sent today
                            </div>
                            <div className="text-[10px] text-muted-foreground">
                              Warmup Cap: {effectiveCap} (Max {inbox.daily_limit}/day)
                            </div>
                          </div>
                        </div>

                        {/* Progress Bar */}
                        <div className="mt-3 w-full bg-muted rounded-full h-1.5 overflow-hidden">
                          <div
                            style={{ width: `${Math.min(100, (inbox.sent_today / effectiveCap) * 100)}%` }}
                            className={`h-full rounded-full transition-all ${
                              isQuarantined ? "bg-muted-foreground" : "bg-primary"
                            }`}
                          />
                        </div>

                        {isQuarantined && inbox.quarantine_reason && (
                          <div className="mt-2.5 p-2 rounded-md bg-muted/30 border border-border text-[10px] text-muted-foreground flex items-center gap-1.5">
                            <AlertTriangle className="w-3 h-3 shrink-0" />
                            <span>
                              <strong className="text-foreground">Automated Tripwire:</strong> {inbox.quarantine_reason}. Cooldown active for 24h to protect IP reputation.
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Pool Simulation Test Outcome */}
              {poolResult && poolResult.selected && (
                <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-muted-foreground" />
                    Pool Test Result: Selected Inbox <code className="text-foreground">{poolResult.selected.email}</code>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Selection Reason: <strong className="text-foreground">{poolResult.selection_reason}</strong> (Deliverability Score: {poolResult.selected.deliverability_score}%)
                  </div>
                  <div className="text-[10px] text-muted-foreground">
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
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Avoid shared ESP tracking domains (e.g. sendgrid.net / mandrillapp.com) that trigger Google Spam filters. Your links are automatically rewritten through your verified custom CNAME subdomain (e.g. <code className="text-foreground">track.{domain}</code>).
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Raw Email Body (Before Rewriting)
                  </label>
                  <textarea
                    rows={7}
                    value={sampleEmailBody}
                    onChange={(e) => setSampleEmailBody(e.target.value)}
                    className="w-full p-3 rounded-lg bg-background border border-border text-xs text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-primary leading-relaxed"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center justify-between">
                    <span>Rewritten Email Body (Via Custom SSL Domain)</span>
                    <span className="text-[10px] text-foreground font-mono">Whitelisted</span>
                  </label>
                  <div className="p-3 rounded-lg bg-muted/30 border border-border text-xs text-foreground font-mono whitespace-pre-wrap leading-relaxed h-[138px] overflow-y-auto">
                    {rewrittenPreview}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-[11px]">
                <div className="p-3 rounded-lg bg-card border border-border flex items-start gap-2.5">
                  <ShieldCheck className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-foreground">Unverified SSL Bypass</div>
                    <p className="text-muted-foreground text-[10px] mt-0.5 leading-relaxed">
                      If the custom tracking subdomain TLS certificate is not active, links remain untouched to avoid browser certificate warnings.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-card border border-border flex items-start gap-2.5">
                  <Flame className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-foreground">Linear Warmup Ramping</div>
                    <p className="text-muted-foreground text-[10px] mt-0.5 leading-relaxed">
                      New inboxes start at 15 sends/day and automatically step up by +5/day to safely condition inbox algorithms.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-card border border-border flex items-start gap-2.5">
                  <Activity className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-foreground">Thread Affinity Locks</div>
                    <p className="text-muted-foreground text-[10px] mt-0.5 leading-relaxed">
                      Followup steps for a lead always dispatch from the identical sender inbox to maintain realistic email thread context.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-t border-border bg-background">
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-primary" />
            <span>
              Deliverability Guard active on all outbound <code className="text-foreground">send_email</code> campaign steps
            </span>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-md bg-card hover:bg-muted border border-border text-xs font-medium text-foreground transition-colors"
            >
              Close Studio
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
