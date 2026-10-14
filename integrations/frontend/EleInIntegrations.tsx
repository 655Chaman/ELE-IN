import { motion, AnimatePresence } from "motion/react"
import { 
  Plug, Zap, CheckCircle2, Search, ArrowRight, ExternalLink, 
  Settings, X, Cpu, Copy, Check, Terminal, Shield, Sparkles, Key, Lock, Calendar,
  Play, AlertCircle, AlertTriangle, RefreshCw, Trash2, Layers, Radio, Send,
  CheckSquare, Square, Info, ChevronRight, Filter, Globe, Code2, PlayCircle, ShieldCheck,
  Activity, Clock, ChevronDown, Eye, Plus, RotateCcw
} from "lucide-react"
import SpotlightCard from "@/components/SpotlightCard"
import ShinyText from "@/components/ShinyText"
import useSWR from "swr"
import { fetchWithAuth } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import { useWorkspace } from "@/contexts/WorkspaceContext"
import { toast } from "sonner"
import { useState, useMemo } from "react"
import { LeadImportProvider } from "@/components/leads/LeadImportContext"
import { HubSpotImport } from "@/components/leads/methods/HubSpotImport"
import { ElesiumLogo } from "@/components/ElesiumLogo"

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface IntegrationItem {
  id: string
  name: string
  category: string
  description: string
  status: "connected" | "available" | "coming_soon"
  badge?: string
  filterCategory: "all" | "ai" | "crm" | "automation" | "calendar" | "security"
}

const BASE_INTEGRATIONS: IntegrationItem[] = [
  { 
    id: "mcp", 
    name: "Model Context Protocol (MCP)", 
    category: "AI Agent Protocol", 
    description: "Allow Cursor, Claude Code, and autonomous AI agents to query campaign analytics, enroll leads, score ICPs, and automate LinkedIn actions via stdio JSON-RPC.", 
    status: "connected",
    badge: "9 Tools Ready",
    filterCategory: "ai"
  },
  { 
    id: "outbound_webhooks", 
    name: "Real-Time Event Webhook Streaming", 
    category: "Outbound Event Pipeline", 
    description: "Stream signed real-time events (lead.connected, lead.email_discovered, lead.meeting_booked, message.sent, lead.enrolled) with HMAC-SHA256 signatures, automated exponential backoff retries, and delivery observability.", 
    status: "connected",
    badge: "Live Event Stream",
    filterCategory: "automation"
  },
  { 
    id: "webhook", 
    name: "Event-Driven Inbound Webhooks", 
    category: "Inbound Intent Engine", 
    description: "Real-time inbound webhook pipeline (/api/hooks/intent/{id}) to instantly enroll leads and launch campaigns from Apollo, 6sense, Clay, or custom cron.", 
    status: "connected",
    badge: "Intent Engine Active",
    filterCategory: "automation"
  },
  { 
    id: "calendly", 
    name: "Calendly & Cal.com", 
    category: "Calendar & Meetings", 
    description: "Auto-halt active outreach sequences the millisecond a prospect books a meeting via Calendly, Cal.com, HubSpot Meetings, or Acuity.", 
    status: "available",
    badge: "Auto-Halt Active",
    filterCategory: "calendar"
  },
  { 
    id: "apollo", 
    name: "Apollo.io B2B Waterfall", 
    category: "Enrichment & CRM", 
    description: "Automated waterfall enrichment for corporate emails, direct-dial phone numbers, and company firmographics directly into outreach sequences.", 
    status: "connected",
    badge: "Active",
    filterCategory: "crm"
  },
  { 
    id: "webshare", 
    name: "Webshare Residential Proxies", 
    category: "Anti-Detect Stealth", 
    description: "Dynamic residential proxy pooling with automated geo-rotation and zero-leak CDP spoofing for safe multi-account scaling.", 
    status: "connected",
    badge: "Stealth On",
    filterCategory: "security"
  },
  { 
    id: "hubspot", 
    name: "HubSpot", 
    category: "CRM", 
    description: "Sync leads, campaigns, and activity data directly to HubSpot with bidirectional field mapping.", 
    status: "available",
    filterCategory: "crm"
  },
  { 
    id: "zapier", 
    name: "Zapier & Make.com", 
    category: "Workflow Automation", 
    description: "Connect 5,000+ apps to trigger Ele-in outreach sequences with instant field mapping, deduplication, and collision protection.", 
    status: "available",
    badge: "Webhook Ready",
    filterCategory: "automation"
  },
  { 
    id: "api_keys", 
    name: "API Keys & Access Tokens", 
    category: "Developer Security", 
    description: "Generate, manage, and rotate cryptographically hashed SHA-256 tokens with granular RBAC permissions for headless integrations.", 
    status: "connected",
    badge: "Key Vault",
    filterCategory: "security"
  },
  { 
    id: "salesforce", 
    name: "Salesforce", 
    category: "CRM", 
    description: "Bidirectional sync for enterprise leads, opportunities, meeting notes, and account ownership.", 
    status: "coming_soon",
    filterCategory: "crm"
  },
  { 
    id: "slack", 
    name: "Slack", 
    category: "Communication", 
    description: "Get real-time alerts for replies, meetings booked, and sentiment shifts directly in your team's Slack channels.", 
    status: "coming_soon",
    filterCategory: "automation"
  }
]

// Pre-configured payload templates for inbound intent webhooks
const SAMPLE_PAYLOADS = {
  apollo: {
    name: "Apollo.io Webhook",
    payload: {
      first_name: "Satya",
      last_name: "Nadella",
      email: "satya.nadella@microsoft.com",
      linkedin_url: "https://www.linkedin.com/in/satyanadella",
      company: "Microsoft",
      title: "Chairman and CEO"
    }
  },
  sixSense: {
    name: "6sense / Demandbase Intent",
    payload: {
      first_name: "Jensen",
      last_name: "Huang",
      email: "jensen.huang@nvidia.com",
      linkedin: "https://www.linkedin.com/in/jenhsunhuang",
      company_name: "NVIDIA",
      intent_score: 94,
      stage: "Decision"
    }
  },
  zapier: {
    name: "Zapier / Make Trigger",
    payload: {
      firstName: "Lisa",
      lastName: "Su",
      work_email: "lisa.su@amd.com",
      person_linkedin_url: "https://www.linkedin.com/in/lisasu",
      organization: "Advanced Micro Devices"
    }
  },
  batch: {
    name: "Batch Lead Array",
    payload: [
      {
        first_name: "Sundar",
        last_name: "Pichai",
        email: "sundar.pichai@google.com",
        linkedin_url: "https://www.linkedin.com/in/sundarpichai",
        company: "Alphabet"
      },
      {
        first_name: "Demis",
        last_name: "Hassabis",
        email: "demis.hassabis@deepmind.com",
        linkedin_url: "https://www.linkedin.com/in/demishassabis",
        company: "Google DeepMind"
      }
    ]
  }
}

export function EleInIntegrations() {
  const { openPaywall } = usePaywall();
  const { activeWorkspaceId } = useWorkspace();
  const { data: billingData } = useSWR<{ tier?: string; tier_limits?: any }>("/api/elein/workspaces/billing", fetcher);
  const tier = billingData?.tier || "FREE";
  const isPro = tier === "PRO" || tier === "ENTERPRISE";

  const { data: hubspotStatus } = useSWR("/api/elein/hubspot/status", fetcher);
  const { data: apiKeysData, mutate: mutateApiKeys } = useSWR("/api/integrations/api-keys", fetcher);
  const { data: dashboardData } = useSWR("/api/elein/dashboard/stats", fetcher);

  const campaigns = dashboardData?.campaigns || dashboardData?.recent_campaigns || [];

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedFilter, setSelectedFilter] = useState<string>("all");

  // Modals state
  const [showHubspotModal, setShowHubspotModal] = useState(false);
  const [showMcpModal, setShowMcpModal] = useState(false);
  const [showCalendlyModal, setShowCalendlyModal] = useState(false);
  const [showWebhookModal, setShowWebhookModal] = useState(false);
  const [showApiKeysModal, setShowApiKeysModal] = useState(false);
  const [showOutboundWebhooksModal, setShowOutboundWebhooksModal] = useState(false);

  // Outbound Webhook Streaming State (Layer 0, 1, 2)
  const { data: webhooksData, mutate: mutateWebhooks } = useSWR<{ status: string; data: any[] }>("/api/webhooks", fetcher);
  const { data: webhookEventsData } = useSWR<{ status: string; events: string[] }>("/api/webhooks/events", fetcher);
  
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [selectedWebhookEvents, setSelectedWebhookEvents] = useState<string[]>([
    "lead.connected", "lead.replied", "lead.email_discovered", "lead.meeting_booked"
  ]);
  const [isCreatingWebhook, setIsCreatingWebhook] = useState(false);
  const [newlyCreatedSecret, setNewlyCreatedSecret] = useState<string | null>(null);
  const [copiedNewSecret, setCopiedNewSecret] = useState(false);
  const [testingEndpointId, setTestingEndpointId] = useState<string | null>(null);
  const [testEndpointResults, setTestEndpointResults] = useState<Record<string, any>>({});
  const [observabilityEndpointId, setObservabilityEndpointId] = useState<string | null>(null);
  const [endpointToDelete, setEndpointToDelete] = useState<string | null>(null);
  const [isDeletingEndpoint, setIsDeletingEndpoint] = useState(false);

  const { data: endpointDeliveriesData, mutate: mutateDeliveries } = useSWR<{ status: string; data: any[] }>(
    observabilityEndpointId ? `/api/webhooks/${observabilityEndpointId}/deliveries` : null,
    fetcher
  );

  // Visual Webhook Studio State (Tabs: Endpoints, Signature Verifier, Zapier/Make Schemas)
  const [webhookStudioTab, setWebhookStudioTab] = useState<"endpoints" | "verifier" | "schemas">("endpoints");
  const [replayingDeliveryId, setReplayingDeliveryId] = useState<string | null>(null);

  // HMAC Verifier State
  const [verifySecret, setVerifySecret] = useState<string>("");
  const [verifySignature, setVerifySignature] = useState<string>("");
  const [verifyTimestamp, setVerifyTimestamp] = useState<string>(() => Math.floor(Date.now() / 1000).toString());
  const [verifyPayload, setVerifyPayload] = useState<string>(() =>
    JSON.stringify({
      event: "lead.replied",
      data: {
        lead_id: "lead_892348",
        lead_name: "Sarah Jenkins",
        lead_email: "sarah.j@enterprise.io",
        company: "Stripe",
        sentiment: "positive",
        reply_snippet: "Thanks for reaching out! Let's talk Tuesday."
      }
    }, null, 2)
  );
  const [verifyShowSecret, setVerifyShowSecret] = useState<boolean>(false);
  const [isVerifyingSignature, setIsVerifyingSignature] = useState<boolean>(false);
  const [signatureVerifyResult, setSignatureVerifyResult] = useState<any | null>(null);

  // Zapier & Make Sample Explorer State
  const [schemaEventType, setSchemaEventType] = useState<string>("lead.replied");
  const { data: sampleSchemaData, isLoading: isLoadingSample } = useSWR<{ status: string; event: string; sample: any }>(
    `/api/webhooks/sample?event=${schemaEventType}`,
    fetcher
  );
  const [copiedSampleJson, setCopiedSampleJson] = useState(false);

  // MCP Key generation state
  const [isGeneratingKey, setIsGeneratingKey] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedJson, setCopiedJson] = useState(false);

  // Webhook Studio State
  const [webhookCampaignId, setWebhookCampaignId] = useState<string>("");
  const [webhookToken, setWebhookToken] = useState<string>("");
  const [webhookPayloadType, setWebhookPayloadType] = useState<keyof typeof SAMPLE_PAYLOADS>("apollo");
  const [webhookPayloadJson, setWebhookPayloadJson] = useState<string>(
    JSON.stringify(SAMPLE_PAYLOADS.apollo.payload, null, 2)
  );
  const [jsonValidationError, setJsonValidationError] = useState<string | null>(null);
  const [isSafeTestMode, setIsSafeTestMode] = useState<boolean>(true);
  const [isTestFiring, setIsTestFiring] = useState<boolean>(false);
  const [testFireResult, setTestFireResult] = useState<any | null>(null);
  const [testFireError, setTestFireError] = useState<string | null>(null);
  const [testFireLatency, setTestFireLatency] = useState<number | null>(null);
  const [copiedWebhookUrl, setCopiedWebhookUrl] = useState(false);
  const [copiedCurlSnippet, setCopiedCurlSnippet] = useState(false);

  // Calendly Auto-Halt Simulator State
  const [testBookingEmail, setTestBookingEmail] = useState("prospect.demo@enterprise.com");
  const [bookingPlatform, setBookingPlatform] = useState<"calendly" | "calcom" | "hubspot">("calendly");
  const [isTestingBooking, setIsTestingBooking] = useState(false);
  const [bookingTestResult, setBookingTestResult] = useState<any | null>(null);
  const [copiedCalendarHook, setCopiedCalendarHook] = useState(false);

  // API Key Vault Drawer/Modal State
  const [newKeyName, setNewKeyName] = useState("Production Inbound Key");
  const [selectedScopes, setSelectedScopes] = useState<string[]>([
    "campaigns:read", "campaigns:write", "leads:read", "leads:write", "browser:execute"
  ]);
  const [isCreatingVaultKey, setIsCreatingVaultKey] = useState(false);
  const [vaultGeneratedKey, setVaultGeneratedKey] = useState<string | null>(null);
  const [copiedVaultKey, setCopiedVaultKey] = useState(false);
  const [keyToRevoke, setKeyToRevoke] = useState<string | null>(null);
  const [isRevokingKey, setIsRevokingKey] = useState(false);

  // Set default campaign for webhook if available
  useMemo(() => {
    if (!webhookCampaignId && campaigns.length > 0) {
      setWebhookCampaignId(campaigns[0].id);
    }
  }, [campaigns, webhookCampaignId]);

  // Set default token if keys exist
  useMemo(() => {
    const keys = apiKeysData?.data || [];
    const activeKey = keys.find((k: any) => k.is_active);
    if (!webhookToken && activeKey) {
      setWebhookToken(activeKey.key_prefix || "ele_live_YOUR_API_TOKEN");
    }
  }, [apiKeysData, webhookToken]);

  const integrations = useMemo(() => {
    return BASE_INTEGRATIONS.map(app => {
      if (app.id === "hubspot" && hubspotStatus?.connected) {
        return { ...app, status: "connected" as const };
      }
      return app;
    }).filter(app => {
      const matchesSearch = app.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                            app.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
                            app.category.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesFilter = selectedFilter === "all" || app.filterCategory === selectedFilter;
      return matchesSearch && matchesFilter;
    });
  }, [hubspotStatus, searchQuery, selectedFilter]);

  const handleConnect = (id: string) => {
    if (id === "hubspot") {
      if (!isPro) {
        openPaywall({ featureName: "HubSpot CRM Integration" });
        toast.info("HubSpot CRM bidirectional sync requires a Growth Pro subscription.");
        return;
      }
      setShowHubspotModal(true);
    } else if (id === "mcp") {
      setShowMcpModal(true);
    } else if (id === "outbound_webhooks") {
      if (!isPro) {
        openPaywall({ featureName: "Real-Time Event Webhook Streaming" });
        toast.info("Real-Time Event Webhook streaming requires a Growth Pro subscription.");
        return;
      }
      setWebhookStudioTab("endpoints");
      setShowOutboundWebhooksModal(true);
    } else if (id === "zapier") {
      if (!isPro) {
        openPaywall({ featureName: "Zapier & Make Automation Hub" });
        toast.info("Zapier & Make workflow triggers require a Growth Pro subscription.");
        return;
      }
      setWebhookStudioTab("schemas");
      setShowOutboundWebhooksModal(true);
    } else if (id === "calendly") {
      setShowCalendlyModal(true);
    } else if (id === "webhook") {
      setShowWebhookModal(true);
    } else if (id === "api_keys") {
      setShowApiKeysModal(true);
    } else if (id === "apollo") {
      toast.success("Apollo.io B2B waterfall is actively resolving emails and titles in sequence nodes.");
    } else if (id === "webshare") {
      toast.success("Webshare residential proxies are active with automatic IP failover.");
    } else {
      toast("Coming soon — we'll notify you when this integration launches");
    }
  }

  // MCP Key generation
  const handleGenerateApiKey = async () => {
    if (!isPro) {
      openPaywall({ featureName: "Autonomous MCP Agent Protocol" });
      toast.info("API Key generation for external AI agents requires Growth Pro.");
      return;
    }
    setIsGeneratingKey(true);
    try {
      const res = await fetchWithAuth("/api/integrations/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "MCP Agent Key",
          scopes: ["campaigns:read", "campaigns:write", "leads:read", "leads:write", "browser:execute"]
        })
      });
      const json = await res.json();
      if (res.ok && json.data?.secret_key) {
        setGeneratedKey(json.data.secret_key);
        setWebhookToken(json.data.secret_key);
        toast.success("New API key generated for MCP Server!");
        mutateApiKeys();
      } else {
        if (res.status === 403) {
          openPaywall({ featureName: "Autonomous MCP Agent Protocol" });
        }
        toast.error(json.detail || "Failed to generate key");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error generating key");
    } finally {
      setIsGeneratingKey(false);
    }
  };

  // API Key Vault: Generate Scoped Key
  const handleCreateVaultKey = async () => {
    if (!isPro) {
      openPaywall({ featureName: "API Key Vault & Custom Scopes" });
      toast.info("API Key generation requires a Growth Pro subscription.");
      return;
    }
    if (!newKeyName.trim()) {
      toast.error("Please enter a name for the API key");
      return;
    }
    setIsCreatingVaultKey(true);
    try {
      const res = await fetchWithAuth("/api/integrations/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newKeyName.trim(),
          scopes: selectedScopes
        })
      });
      const json = await res.json();
      if (res.ok && json.data?.secret_key) {
        setVaultGeneratedKey(json.data.secret_key);
        setWebhookToken(json.data.secret_key);
        toast.success(`Key '${newKeyName}' issued successfully!`);
        mutateApiKeys();
      } else {
        toast.error(json.detail || "Failed to issue key");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error issuing key");
    } finally {
      setIsCreatingVaultKey(false);
    }
  };

  // API Key Vault: Revoke Key
  const handleRevokeKey = async (keyId: string) => {
    setIsRevokingKey(true);
    try {
      const res = await fetchWithAuth(`/api/integrations/api-keys/${keyId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        toast.success("API key revoked. Any future request using this key will be rejected.");
        setKeyToRevoke(null);
        mutateApiKeys();
      } else {
        const json = await res.json();
        toast.error(json.detail || "Failed to revoke key");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error revoking key");
    } finally {
      setIsRevokingKey(false);
    }
  };

  // ── Outbound Webhooks Management (Paranoia Layer 0, 1, 2) ──
  const handleCreateWebhookEndpoint = async () => {
    if (!isPro) {
      openPaywall({ featureName: "Real-Time Event Webhook Streaming" });
      toast.info("Custom webhook streaming requires Growth Pro.");
      return;
    }
    const cleanUrl = newWebhookUrl.trim();
    if (!cleanUrl) {
      toast.error("Please enter a destination webhook URL");
      return;
    }
    if (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://")) {
      toast.error("Webhook URL must start with http:// or https://");
      return;
    }
    if (
      cleanUrl.includes("localhost") || 
      cleanUrl.includes("127.0.0.1") || 
      cleanUrl.includes("192.168.") || 
      cleanUrl.includes("10.") ||
      cleanUrl.includes("169.254.")
    ) {
      toast.error("SSRF Protection: Webhook URL cannot point to internal or loopback IP addresses.");
      return;
    }
    if (selectedWebhookEvents.length === 0) {
      toast.error("Please select at least one subscribed event");
      return;
    }

    setIsCreatingWebhook(true);
    try {
      const res = await fetchWithAuth("/api/webhooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: cleanUrl,
          event_types: selectedWebhookEvents
        })
      });
      const json = await res.json();
      if (res.ok && json.data) {
        setNewlyCreatedSecret(json.data.signing_secret);
        setNewWebhookUrl("");
        toast.success("Webhook endpoint successfully created!");
        mutateWebhooks();
      } else {
        toast.error(json.detail || "Failed to create webhook endpoint");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error creating webhook endpoint");
    } finally {
      setIsCreatingWebhook(false);
    }
  };

  const handleToggleWebhookActive = async (ep: any) => {
    try {
      const res = await fetchWithAuth(`/api/webhooks/${ep.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !ep.is_active })
      });
      if (res.ok) {
        toast.success(`Webhook endpoint ${ep.is_active ? "disabled" : "activated"}`);
        mutateWebhooks();
      } else {
        const json = await res.json();
        toast.error(json.detail || "Failed to update webhook");
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to toggle webhook state");
    }
  };

  const handleDeleteWebhookEndpoint = async (endpointId: string) => {
    setIsDeletingEndpoint(true);
    try {
      const res = await fetchWithAuth(`/api/webhooks/${endpointId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        toast.success("Webhook endpoint deleted");
        setEndpointToDelete(null);
        if (observabilityEndpointId === endpointId) {
          setObservabilityEndpointId(null);
        }
        mutateWebhooks();
      } else {
        const json = await res.json();
        toast.error(json.detail || "Failed to delete webhook");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error deleting webhook");
    } finally {
      setIsDeletingEndpoint(false);
    }
  };

  const handleTestWebhookPing = async (endpointId: string) => {
    setTestingEndpointId(endpointId);
    try {
      const res = await fetchWithAuth(`/api/webhooks/${endpointId}/test`, {
        method: "POST"
      });
      const json = await res.json();
      setTestEndpointResults(prev => ({ ...prev, [endpointId]: json }));
      if (json.status === "success") {
        toast.success(`Ping succeeded! HTTP ${json.status_code} in ${json.latency_ms}ms`);
      } else {
        toast.error(`Ping failed: ${json.response_body || json.message || "HTTP Error"}`);
      }
      if (observabilityEndpointId === endpointId) {
        mutateDeliveries();
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to send test ping");
    } finally {
      setTestingEndpointId(null);
    }
  };

  // Replay failed or past delivery (Paranoia Layer 0, 1, 2)
  const handleReplayDelivery = async (deliveryId: string) => {
    setReplayingDeliveryId(deliveryId);
    try {
      const res = await fetchWithAuth(`/api/webhooks/deliveries/${deliveryId}/replay`, {
        method: "POST"
      });
      const json = await res.json();
      if (res.ok && json.status === "success") {
        toast.success(`Delivery replayed successfully! HTTP ${json.status_code} (${json.latency_ms}ms)`);
        mutateDeliveries();
      } else {
        toast.error(json.detail || json.message || "Failed to replay delivery");
        mutateDeliveries();
      }
    } catch (e: any) {
      toast.error(e.message || "Network error replaying delivery");
    } finally {
      setReplayingDeliveryId(null);
    }
  };

  // HMAC Signature Diagnostic Tool (Paranoia Layer 0, 1, 2)
  const handleVerifySignature = async () => {
    if (!verifySecret.trim()) {
      toast.error("Please provide the signing secret to verify against.");
      return;
    }
    if (!verifySignature.trim()) {
      toast.error("Please provide the EleIn-Signature header value.");
      return;
    }
    if (!verifyPayload.trim()) {
      toast.error("Please provide the payload body to verify.");
      return;
    }

    setIsVerifyingSignature(true);
    setSignatureVerifyResult(null);
    try {
      const res = await fetchWithAuth("/api/webhooks/verify-signature", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payload: verifyPayload,
          secret: verifySecret.trim(),
          signature: verifySignature.trim(),
          timestamp: verifyTimestamp.trim() || Math.floor(Date.now() / 1000).toString(),
          tolerance_seconds: 300
        })
      });
      const json = await res.json();
      if (res.ok && json.result) {
        setSignatureVerifyResult(json.result);
        if (json.result.is_valid) {
          toast.success("Signature match verified! HMAC-SHA256 signature is authentic.");
        } else {
          toast.error(json.result.reason || "Signature verification failed.");
        }
      } else {
        toast.error(json.detail || "Failed to verify signature");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error verifying signature");
    } finally {
      setIsVerifyingSignature(false);
    }
  };

  // Change preset payload in webhook studio
  const handleSelectPreset = (key: keyof typeof SAMPLE_PAYLOADS) => {
    setWebhookPayloadType(key);
    let payload = SAMPLE_PAYLOADS[key].payload;
    if (isSafeTestMode) {
      const randomSuffix = Math.floor(1000 + Math.random() * 9000);
      if (Array.isArray(payload)) {
        payload = payload.map((p, i) => ({
          ...p,
          email: `test_lead_${randomSuffix}_${i}@elein-preview.local`
        }));
      } else {
        payload = {
          ...payload,
          email: `test_lead_${randomSuffix}@elein-preview.local`
        } as any;
      }
    }
    setWebhookPayloadJson(JSON.stringify(payload, null, 2));
    setJsonValidationError(null);
  };

  // Update JSON with validation
  const handleJsonChange = (val: string) => {
    setWebhookPayloadJson(val);
    try {
      JSON.parse(val);
      setJsonValidationError(null);
    } catch (err: any) {
      setJsonValidationError(err.message);
    }
  };

  // Safe mode toggle handler
  const handleToggleSafeMode = () => {
    const nextSafe = !isSafeTestMode;
    setIsSafeTestMode(nextSafe);
    try {
      const current = JSON.parse(webhookPayloadJson);
      const randomSuffix = Math.floor(1000 + Math.random() * 9000);
      if (nextSafe) {
        if (Array.isArray(current)) {
          const updated = current.map((item, i) => ({
            ...item,
            email: `test_lead_${randomSuffix}_${i}@elein-preview.local`
          }));
          setWebhookPayloadJson(JSON.stringify(updated, null, 2));
        } else {
          setWebhookPayloadJson(JSON.stringify({
            ...current,
            email: `test_lead_${randomSuffix}@elein-preview.local`
          }, null, 2));
        }
      }
    } catch {
      // ignore parse err
    }
  };

  // Computed Webhook URL
  const webhookUrl = useMemo(() => {
    const origin = typeof window !== "undefined" ? window.location.origin : "https://app.ele-in.com";
    const campId = webhookCampaignId || "CAMPAIGN_ID";
    const token = webhookToken || "YOUR_API_TOKEN";
    return `${origin}/api/hooks/intent/${campId}?token=${encodeURIComponent(token)}`;
  }, [webhookCampaignId, webhookToken]);

  // cURL Command generator
  const curlCommand = useMemo(() => {
    let cleanJson = webhookPayloadJson;
    try {
      cleanJson = JSON.stringify(JSON.parse(webhookPayloadJson));
    } catch {
      // keep raw
    }
    return `curl -X POST "${webhookUrl}" \\\n  -H "Content-Type: application/json" \\\n  -d '${cleanJson}'`;
  }, [webhookUrl, webhookPayloadJson]);

  // Test Fire Inbound Webhook
  const handleTestFireWebhook = async () => {
    if (!webhookCampaignId) {
      toast.error("Please select a target campaign first");
      return;
    }
    if (!webhookToken) {
      toast.error("Please provide or generate an API token");
      return;
    }
    if (jsonValidationError) {
      toast.error("Fix JSON syntax errors before firing");
      return;
    }

    let parsedBody;
    try {
      parsedBody = JSON.parse(webhookPayloadJson);
    } catch (e: any) {
      toast.error("Invalid JSON payload: " + e.message);
      return;
    }

    setIsTestFiring(true);
    setTestFireResult(null);
    setTestFireError(null);
    const startTime = performance.now();

    // Paranoia Layer 1: 15-second AbortController watchdog
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    try {
      const res = await fetch(`/api/hooks/intent/${webhookCampaignId}?token=${encodeURIComponent(webhookToken)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsedBody),
        signal: controller.signal
      });

      const elapsed = Math.round(performance.now() - startTime);
      setTestFireLatency(elapsed);

      let data;
      try {
        data = await res.json();
      } catch {
        data = { status: res.statusText };
      }

      if (res.ok) {
        setTestFireResult(data);
        toast.success(`Webhook test passed! (${elapsed}ms) - Enrolled: ${data.enrolled ?? 0}, Skipped: ${data.skipped ?? 0}`);
      } else {
        const msg = data.detail || `Server returned HTTP ${res.status}`;
        setTestFireError(msg);
        toast.error(`Webhook test failed (${res.status}): ${msg}`);
      }
    } catch (e: any) {
      const elapsed = Math.round(performance.now() - startTime);
      setTestFireLatency(elapsed);
      if (e.name === "AbortError") {
        setTestFireError("Request timed out after 15 seconds. Ensure the backend engine is running.");
        toast.error("Webhook request timed out");
      } else {
        setTestFireError(e.message || "Network error firing webhook");
        toast.error(e.message || "Failed to reach endpoint");
      }
    } finally {
      clearTimeout(timeoutId);
      setIsTestFiring(false);
    }
  };

  // Simulate Calendly Booking Auto-Halt
  const handleSimulateBooking = async () => {
    if (!testBookingEmail || !testBookingEmail.includes("@")) {
      toast.error("Please enter a valid prospect email to test auto-halt");
      return;
    }
    setIsTestingBooking(true);
    setBookingTestResult(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);

    let samplePayload: any = {
      event: "invitee.created",
      email: testBookingEmail.trim().toLowerCase(),
      created_at: new Date().toISOString()
    };

    if (bookingPlatform === "calcom") {
      samplePayload = {
        triggerEvent: "BOOKING_CREATED",
        payload: {
          attendees: [{ email: testBookingEmail.trim().toLowerCase() }],
          booking: { title: "Executive Intro Call" }
        }
      };
    } else if (bookingPlatform === "hubspot") {
      samplePayload = {
        attendees: [{ email: testBookingEmail.trim().toLowerCase() }]
      };
    }

    try {
      const res = await fetch(`/api/hooks/booking/${activeWorkspaceId || "test"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(samplePayload),
        signal: controller.signal
      });
      const data = await res.json();
      setBookingTestResult(data);
      if (data.status === "success") {
        toast.success(`Auto-Halt Triggered! Outreach halted for '${testBookingEmail}'.`);
      } else if (data.status === "ignored") {
        toast.info(`Webhook received: ${data.reason}`);
      } else {
        toast.error("Unexpected response from booking webhook");
      }
    } catch (e: any) {
      if (e.name === "AbortError") {
        toast.error("Booking simulation timed out");
      } else {
        toast.error(e.message || "Failed to simulate booking");
      }
    } finally {
      clearTimeout(timeoutId);
      setIsTestingBooking(false);
    }
  };

  const mcpConfigSnippet = JSON.stringify({
    mcpServers: {
      elein: {
        command: "uv",
        args: [
          "run",
          "/Users/krdeeksha/Ele-in/mcp/start.sh"
        ],
        env: {
          ELEIN_API_KEY: generatedKey || webhookToken || "your_elein_api_key_here"
        }
      }
    }
  }, null, 2);

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-8 py-10 max-w-6xl mx-auto font-sans">
      {/* Top Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Plug size={24} className="text-primary" />
            <ShinyText text="Integrations & Inbound Engine" disabled={false} speed={3} className="" />
          </h1>
          <p className="text-xs text-muted-foreground">
            Connect Ele-in to CRMs, residential stealth proxies, calendar auto-halt webhooks, and autonomous AI developer agents.
          </p>
        </div>

        {/* Quick Access Actions */}
        <div className="flex items-center gap-2 self-stretch sm:self-auto">
          <button
            onClick={() => setShowApiKeysModal(true)}
            className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-background hover:bg-muted border border-border/60 text-foreground transition-all shadow-sm cursor-pointer"
          >
            <Key size={14} className="text-amber-400" />
            <span>API Key Vault</span>
          </button>
          <button
            onClick={() => setShowWebhookModal(true)}
            className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm cursor-pointer"
          >
            <Zap size={14} className="fill-current" />
            <span>Inbound Webhook Studio</span>
          </button>
        </div>
      </motion.div>

      {/* ─── IN-SITU PAY RAMP: DEVELOPER PROTOCOLS & CRM GATEWAY ─── */}
      {!isPro && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 p-5 sm:p-6 rounded-3xl bg-gradient-to-r from-indigo-950/40 via-blue-950/30 to-background border border-indigo-500/20 shadow-xl relative overflow-hidden flex flex-col md:flex-row md:items-center justify-between gap-5"
        >
          <div className="flex items-start sm:items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0 text-indigo-400">
              <Cpu className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-foreground">
                  Developer Protocols & Enterprise CRM Gated
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 flex items-center gap-1">
                  <Lock size={10} /> Pro Plan Feature
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed">
                Growth Pro unlocks <strong>HubSpot CRM bidirectional synchronization</strong>, custom <strong>real-time event Webhooks</strong>, and scoped API keys for <strong>Cursor, Claude Code, and autonomous AI agents</strong> via the Model Context Protocol.
              </p>
            </div>
          </div>

          <button
            onClick={() => openPaywall({ featureName: "HubSpot CRM & Developer Protocols" })}
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white shadow-md shadow-indigo-600/20 transition-all cursor-pointer whitespace-nowrap self-start md:self-auto shrink-0"
          >
            <Zap size={14} className="fill-current" />
            <span>Unlock All Integrations</span>
            <ArrowRight size={14} />
          </button>
        </motion.div>
      )}

      {/* ── SEARCH & CATEGORY FILTER DOCK ── */}
      <div className="mb-6 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search integrations, tools, and protocols..."
            className="w-full bg-muted/20 border border-border/50 rounded-xl pl-9 pr-4 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/50 transition-colors"
          />
          {searchQuery && (
            <button 
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {[
            { id: "all", label: "All Protocols" },
            { id: "ai", label: "AI & Agents" },
            { id: "automation", label: "Webhooks & Automation" },
            { id: "calendar", label: "Meeting Protection" },
            { id: "crm", label: "CRM & Data" },
            { id: "security", label: "Security & Keys" },
          ].map(f => (
            <button
              key={f.id}
              onClick={() => setSelectedFilter(f.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all cursor-pointer ${
                selectedFilter === f.id
                  ? "bg-primary text-primary-foreground font-semibold shadow-xs"
                  : "bg-muted/30 text-muted-foreground hover:text-foreground hover:bg-muted/50 border border-border/30"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── INTEGRATIONS GRID ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {integrations.map((app, i) => (
          <motion.div
            key={app.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            <SpotlightCard className="h-full flex flex-col p-6 rounded-2xl border border-border/50 bg-muted/10 backdrop-blur-md hover:border-border transition-all">
              <div className="flex justify-between items-start mb-4">
                <div className={`w-12 h-12 rounded-2xl border flex items-center justify-center ${
                  app.id === "mcp" 
                    ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-400" 
                    : app.id === "webhook"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                    : app.id === "apollo"
                    ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                    : app.id === "webshare"
                    ? "bg-teal-500/10 border-teal-500/30 text-teal-400"
                    : app.id === "calendly"
                    ? "bg-sky-500/10 border-sky-500/30 text-sky-400"
                    : app.id === "zapier"
                    ? "bg-orange-500/10 border-orange-500/30 text-orange-400"
                    : app.id === "api_keys"
                    ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                    : "bg-background border-border/50 text-primary"
                }`}>
                  {app.id === "mcp" ? <ElesiumLogo size={22} /> : 
                   app.id === "webhook" ? <Terminal size={22} /> :
                   app.id === "webshare" ? <Shield size={22} /> : 
                   app.id === "calendly" ? <Calendar size={22} /> : 
                   app.id === "api_keys" ? <Key size={22} /> :
                   app.id === "zapier" ? <Zap size={22} /> :
                   <Zap size={20} />}
                </div>
                {app.status === "connected" ? (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-success/10 text-success text-[10px] font-bold">
                    <CheckCircle2 size={12} /> {app.badge || "Connected"}
                  </span>
                ) : (app.id === "hubspot") && !isPro ? (
                  <span className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-amber-500/10 text-amber-400 text-[10px] font-bold border border-amber-500/20">
                    <Lock size={10} /> Pro Plan
                  </span>
                ) : app.status === "coming_soon" ? (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted/50 text-muted-foreground text-[10px] font-bold">
                    Coming Soon
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted text-muted-foreground text-[10px] font-bold">
                    {app.badge || "Available"}
                  </span>
                )}
              </div>
              
              <h3 className="text-base font-bold text-foreground tracking-tight mb-1">
                {app.name}
              </h3>
              <p className="text-[10px] font-semibold text-primary/80 mb-3 tracking-wider uppercase">
                {app.category}
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6 flex-1">
                {app.description}
              </p>

              <div className="pt-4 border-t border-border/50 mt-auto">
                {app.id === "hubspot" && !isPro ? (
                  <button 
                    onClick={() => handleConnect(app.id)}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 text-white rounded-lg text-xs font-bold transition-all shadow-sm cursor-pointer"
                  >
                    <Lock size={12} /> Unlock with Pro
                  </button>
                ) : app.id === "webhook" ? (
                  <button 
                    onClick={() => handleConnect(app.id)}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition-all shadow-sm cursor-pointer"
                  >
                    <Terminal size={14} /> Open Webhook Studio
                  </button>
                ) : app.id === "api_keys" ? (
                  <button 
                    onClick={() => handleConnect(app.id)}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-background hover:bg-muted border border-border/60 rounded-lg text-xs font-bold text-foreground transition-all shadow-sm cursor-pointer"
                  >
                    <Key size={14} className="text-amber-400" /> Manage Key Vault
                  </button>
                ) : app.status === "connected" ? (
                  <button 
                    onClick={() => handleConnect(app.id)}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-background hover:bg-muted border border-border/50 rounded-lg text-xs font-bold text-foreground transition-all shadow-sm cursor-pointer"
                  >
                    <Settings size={14} className="text-muted-foreground" /> Manage
                  </button>
                ) : app.status === "coming_soon" ? (
                  <button disabled className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-muted text-muted-foreground rounded-lg text-xs font-bold cursor-not-allowed opacity-70">
                    Coming Soon
                  </button>
                ) : (
                  <button 
                    onClick={() => handleConnect(app.id)} 
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-xs font-bold transition-all shadow-sm cursor-pointer"
                  >
                    Configure
                  </button>
                )}
              </div>
            </SpotlightCard>
          </motion.div>
        ))}
      </div>

      {/* ── HubSpot Modal ── */}
      {showHubspotModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="bg-card w-full max-w-md rounded-2xl border shadow-xl p-6 relative">
            <button 
              onClick={() => setShowHubspotModal(false)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground z-10"
            >
              <X size={20} />
            </button>
            <LeadImportProvider>
              <HubSpotImport onClose={() => setShowHubspotModal(false)} mode="connect" />
            </LeadImportProvider>
          </div>
        </div>
      )}

      {/* ── MCP Configuration Modal (Paranoia Layer 2) ── */}
      {showMcpModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-md">
          <div className="bg-card w-full max-w-2xl rounded-3xl border border-indigo-500/20 shadow-2xl p-8 relative max-h-[90vh] overflow-y-auto">
            <button 
              onClick={() => setShowMcpModal(false)}
              className="absolute top-6 right-6 p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
            >
              <X size={20} />
            </button>

            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                <ElesiumLogo size={24} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
                  Model Context Protocol (MCP) Server
                  <ElesiumLogo size={16} />
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">Connect Cursor, Claude Code, or Codex agents to Ele-in natively.</p>
              </div>
            </div>

            <div className="space-y-6">
              {/* Tool list */}
              <div className="p-4 rounded-2xl bg-muted/20 border border-border/50">
                <h4 className="text-xs font-bold text-foreground uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Terminal size={14} className="text-indigo-400" />
                  9 Registered Native MCP Tools
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {[
                    "elein_list_campaigns",
                    "elein_enroll_leads",
                    "elein_get_campaign_analytics",
                    "elein_pause_campaign",
                    "elein_resume_campaign",
                    "elein_get_lead_status",
                    "elein_score_lead_icp",
                    "elein_get_person_profile",
                    "elein_send_linkedin_message"
                  ].map(t => (
                    <div key={t} className="text-[11px] font-mono px-2 py-1 rounded-lg bg-background border border-border/40 text-foreground truncate flex items-center gap-1.5">
                      <Check size={11} className="text-emerald-500 shrink-0" />
                      <span>{t}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* API Key Generation */}
              <div className="p-5 rounded-2xl border border-border/60 bg-background/50">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Key size={14} className="text-amber-400" />
                    Agent Authentication Key
                  </span>
                  {!isPro ? (
                    <button
                      onClick={() => {
                        openPaywall({ featureName: "Autonomous MCP Agent Protocol" });
                        toast.info("MCP Developer Protocol & API keys require Growth Pro.");
                      }}
                      className="px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white text-xs font-bold rounded-lg transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                    >
                      <Lock size={12} />
                      <span>Unlock with Pro</span>
                    </button>
                  ) : (
                    <button
                      onClick={handleGenerateApiKey}
                      disabled={isGeneratingKey}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-lg transition-all shadow-sm flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                    >
                      {isGeneratingKey ? "Generating..." : "Generate New Key"}
                    </button>
                  )}
                </div>

                {generatedKey ? (
                  <div className="space-y-2">
                    <p className="text-[11px] text-amber-400 font-semibold">Copy this key now. It will never be shown again:</p>
                    <div className="flex items-center gap-2 bg-muted/40 p-2.5 rounded-xl border border-border/50 font-mono text-xs">
                      <span className="flex-1 truncate text-foreground">{generatedKey}</span>
                      <button 
                        onClick={() => {
                          navigator.clipboard.writeText(generatedKey);
                          setCopiedKey(true);
                          toast.success("API key copied to clipboard!");
                          setTimeout(() => setCopiedKey(false), 2000);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-background border border-border hover:bg-muted text-foreground text-xs flex items-center gap-1 font-sans font-semibold cursor-pointer"
                      >
                        {copiedKey ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                        {copiedKey ? "Copied" : "Copy"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Click "Generate New Key" to create a scoped token for your external AI agent environment.
                  </p>
                )}
              </div>

              {/* Configuration Snippet */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Cursor (~/.cursor/mcp.json) & Claude Desktop Configuration:
                  </span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(mcpConfigSnippet);
                      setCopiedJson(true);
                      toast.success("Configuration snippet copied!");
                      setTimeout(() => setCopiedJson(false), 2000);
                    }}
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 cursor-pointer"
                  >
                    {copiedJson ? <Check size={12} /> : <Copy size={12} />}
                    {copiedJson ? "Copied JSON" : "Copy JSON"}
                  </button>
                </div>
                <pre className="p-4 rounded-2xl bg-slate-950 text-slate-200 text-xs font-mono overflow-x-auto border border-border/40">
                  {mcpConfigSnippet}
                </pre>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={() => setShowMcpModal(false)}
                  className="px-6 py-2.5 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-bold transition-all cursor-pointer"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Webhook & Inbound Intent Studio Modal (Paranoia Layer 0-2) ── */}
      {showWebhookModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/85 backdrop-blur-md">
          <div className="bg-card w-full max-w-3xl rounded-3xl border border-emerald-500/20 shadow-2xl p-6 sm:p-8 relative max-h-[92vh] overflow-y-auto">
            <button 
              onClick={() => setShowWebhookModal(false)}
              className="absolute top-6 right-6 p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
            >
              <X size={20} />
            </button>

            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <Terminal size={24} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
                  Inbound Intent Webhook Studio
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    Live Engine
                  </span>
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Stream leads from Apollo, 6sense, Zapier, Clay, or curl directly into running campaigns with automatic sender fleet load balancing.
                </p>
              </div>
            </div>

            <div className="space-y-6">
              {/* Target Campaign & Token Selectors */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 rounded-2xl bg-muted/20 border border-border/50">
                <div>
                  <label className="text-xs font-bold text-foreground flex items-center gap-1.5 mb-1.5">
                    <Layers size={13} className="text-emerald-400" />
                    Target Campaign Destination
                  </label>
                  {campaigns.length === 0 ? (
                    <div className="text-xs text-amber-400 bg-amber-500/10 p-2.5 rounded-xl border border-amber-500/20">
                      No campaigns found. Create a campaign first to route inbound webhooks.
                    </div>
                  ) : (
                    <select
                      value={webhookCampaignId}
                      onChange={(e) => setWebhookCampaignId(e.target.value)}
                      className="w-full bg-background border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:border-emerald-500/50"
                    >
                      {campaigns.map((c: any) => (
                        <option key={c.id} value={c.id}>
                          {c.name} ({c.status})
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <Key size={13} className="text-amber-400" />
                      API Authentication Token
                    </label>
                    <button
                      onClick={() => setShowApiKeysModal(true)}
                      className="text-[11px] text-primary hover:underline font-semibold"
                    >
                      Manage Keys
                    </button>
                  </div>
                  <input
                    type="text"
                    value={webhookToken}
                    onChange={(e) => setWebhookToken(e.target.value)}
                    placeholder="ele_live_..."
                    className="w-full bg-background border border-border/60 rounded-xl px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-emerald-500/50"
                  />
                </div>
              </div>

              {/* Endpoint URL Presentation */}
              <div className="p-4 rounded-2xl border border-border/60 bg-background/50">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Globe size={13} className="text-emerald-400" />
                    Webhook POST Endpoint URL
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(webhookUrl);
                        setCopiedWebhookUrl(true);
                        toast.success("Webhook URL copied!");
                        setTimeout(() => setCopiedWebhookUrl(false), 2000);
                      }}
                      className="text-xs text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1 cursor-pointer"
                    >
                      {copiedWebhookUrl ? <Check size={12} /> : <Copy size={12} />}
                      {copiedWebhookUrl ? "Copied URL" : "Copy URL"}
                    </button>
                    <span className="text-muted-foreground/40">|</span>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(curlCommand);
                        setCopiedCurlSnippet(true);
                        toast.success("cURL command copied!");
                        setTimeout(() => setCopiedCurlSnippet(false), 2000);
                      }}
                      className="text-xs text-primary hover:text-primary/80 font-semibold flex items-center gap-1 cursor-pointer"
                    >
                      {copiedCurlSnippet ? <Check size={12} /> : <Terminal size={12} />}
                      {copiedCurlSnippet ? "Copied cURL" : "Copy cURL"}
                    </button>
                  </div>
                </div>

                <div className="bg-muted/40 p-2.5 rounded-xl border border-border/50 font-mono text-xs text-foreground truncate select-all">
                  {webhookUrl}
                </div>
              </div>

              {/* Payload Template Presets & Editor */}
              <div className="space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Code2 size={13} className="text-indigo-400" />
                    Inbound Payload Schema & Presets
                  </span>

                  <div className="flex items-center gap-1.5">
                    {(Object.keys(SAMPLE_PAYLOADS) as Array<keyof typeof SAMPLE_PAYLOADS>).map((key) => (
                      <button
                        key={key}
                        onClick={() => handleSelectPreset(key)}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all cursor-pointer ${
                          webhookPayloadType === key
                            ? "bg-emerald-600 text-white shadow-xs"
                            : "bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground border border-border/40"
                        }`}
                      >
                        {SAMPLE_PAYLOADS[key].name}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Safe Test Mode Toggle (Paranoia Layer 2) */}
                <div className="flex items-center justify-between p-2.5 rounded-xl bg-muted/20 border border-border/40 text-xs">
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={14} className={isSafeTestMode ? "text-emerald-400" : "text-muted-foreground"} />
                    <span className="text-muted-foreground">
                      Safe Test Mode: Uses isolated <code className="text-foreground">@elein-preview.local</code> test identities
                    </span>
                  </div>
                  <button
                    onClick={handleToggleSafeMode}
                    className={`px-2.5 py-0.5 rounded-md text-[11px] font-bold transition-all cursor-pointer ${
                      isSafeTestMode
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : "bg-muted text-muted-foreground border border-border/40"
                    }`}
                  >
                    {isSafeTestMode ? "Safe Mode ON" : "Off (Real Data)"}
                  </button>
                </div>

                {/* JSON Editor */}
                <div className="relative">
                  <textarea
                    rows={7}
                    value={webhookPayloadJson}
                    onChange={(e) => handleJsonChange(e.target.value)}
                    className={`w-full p-3 rounded-2xl bg-slate-950 text-slate-200 text-xs font-mono border focus:outline-none transition-colors ${
                      jsonValidationError ? "border-rose-500/60 focus:border-rose-500" : "border-border/40 focus:border-emerald-500/50"
                    }`}
                  />
                  {jsonValidationError && (
                    <div className="mt-1 text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                      <AlertCircle size={12} />
                      JSON Syntax Error: {jsonValidationError}
                    </div>
                  )}
                </div>
              </div>

              {/* Live Test Fire Action Dock & Response Console */}
              <div className="p-4 rounded-2xl bg-muted/20 border border-border/50 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <PlayCircle size={14} className="text-emerald-400" />
                      Live Inbound Webhook Test Simulator
                    </h4>
                    <p className="text-[11px] text-muted-foreground">
                      Executes an actual HTTP POST against the backend engine to verify authentication, field mapping, and fleet allocation.
                    </p>
                  </div>

                  <button
                    onClick={handleTestFireWebhook}
                    disabled={isTestFiring || !!jsonValidationError}
                    className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white transition-all shadow-sm cursor-pointer whitespace-nowrap"
                  >
                    {isTestFiring ? (
                      <>
                        <RefreshCw size={13} className="animate-spin" />
                        <span>Executing...</span>
                      </>
                    ) : (
                      <>
                        <Zap size={13} className="fill-current" />
                        <span>Test Fire Webhook</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Test Result Display */}
                {testFireResult && (
                  <div className="p-3.5 rounded-xl bg-emerald-950/30 border border-emerald-500/30 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-emerald-400 flex items-center gap-1.5">
                        <CheckCircle2 size={14} /> 200 OK — Ingest Succeeded
                      </span>
                      {testFireLatency && (
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {testFireLatency}ms
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                      <div className="p-2 rounded-lg bg-background/50 border border-border/40">
                        <span className="text-muted-foreground block text-[10px]">ENROLLED LEADS</span>
                        <span className="text-emerald-400 font-bold text-sm">{testFireResult.enrolled ?? 0}</span>
                      </div>
                      <div className="p-2 rounded-lg bg-background/50 border border-border/40">
                        <span className="text-muted-foreground block text-[10px]">SKIPPED / COLLIDED</span>
                        <span className="text-foreground font-bold text-sm">{testFireResult.skipped ?? 0}</span>
                      </div>
                    </div>
                  </div>
                )}

                {testFireError && (
                  <div className="p-3.5 rounded-xl bg-rose-950/30 border border-rose-500/30 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-rose-400 flex items-center gap-1.5">
                        <AlertTriangle size={14} /> Execution Rejected
                      </span>
                      {testFireLatency && (
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {testFireLatency}ms
                        </span>
                      )}
                    </div>
                    <p className="text-rose-200 text-xs font-mono">{testFireError}</p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Tip: Verify that the API token is active and the campaign has sender accounts linked.
                    </p>
                  </div>
                )}
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={() => setShowWebhookModal(false)}
                  className="px-6 py-2.5 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-bold transition-all cursor-pointer"
                >
                  Close Studio
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Calendly & Cal.com Auto-Halt Modal with Live Verification Simulator ── */}
      {showCalendlyModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-md">
          <div className="bg-card w-full max-w-2xl rounded-3xl border border-sky-500/20 shadow-2xl p-8 relative max-h-[90vh] overflow-y-auto">
            <button 
              onClick={() => setShowCalendlyModal(false)}
              className="absolute top-6 right-6 p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
            >
              <X size={20} />
            </button>

            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-2xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
                <Calendar size={24} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
                  Calendar Booking Auto-Halt
                  <Sparkles size={16} className="text-sky-400" />
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Universal inbound webhook for Calendly, Cal.com, HubSpot Meetings, and Acuity.
                </p>
              </div>
            </div>

            <div className="space-y-6">
              {/* How it works banner */}
              <div className="p-4 rounded-2xl bg-sky-500/5 border border-sky-500/20 text-xs text-muted-foreground leading-relaxed">
                <span className="font-semibold text-sky-400 block mb-1">Instant Outreach Protection (Paranoia Guard)</span>
                When a prospect books a meeting via your scheduling link, this webhook matches their email, marks them as <strong className="text-foreground">Meeting Booked</strong>, and immediately halts all active in-flight LinkedIn messages and follow-up sequences across your campaigns.
              </div>

              {/* Webhook Endpoint */}
              <div className="p-5 rounded-2xl border border-border/60 bg-background/50">
                <span className="text-xs font-bold text-foreground flex items-center gap-1.5 mb-2">
                  <Terminal size={14} className="text-sky-400" />
                  Your Workspace Calendar Webhook URL
                </span>
                <p className="text-[11px] text-muted-foreground mb-3">
                  Paste this URL into your Calendly, Cal.com, or booking platform webhook settings:
                </p>

                <div className="flex items-center gap-2 bg-muted/40 p-2.5 rounded-xl border border-border/50 font-mono text-xs">
                  <span className="flex-1 truncate text-foreground">
                    {typeof window !== "undefined" ? window.location.origin : ""}/api/hooks/booking/{activeWorkspaceId || "YOUR_WORKSPACE_ID"}
                  </span>
                  <button 
                    onClick={() => {
                      const url = `${typeof window !== "undefined" ? window.location.origin : ""}/api/hooks/booking/${activeWorkspaceId || "YOUR_WORKSPACE_ID"}`;
                      navigator.clipboard.writeText(url);
                      setCopiedCalendarHook(true);
                      toast.success("Webhook URL copied to clipboard!");
                      setTimeout(() => setCopiedCalendarHook(false), 2000);
                    }}
                    className="px-2.5 py-1 rounded-lg bg-background border border-border hover:bg-muted text-foreground text-xs flex items-center gap-1 font-sans font-semibold shrink-0 cursor-pointer"
                  >
                    {copiedCalendarHook ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                    {copiedCalendarHook ? "Copied" : "Copy URL"}
                  </button>
                </div>
              </div>

              {/* Live Auto-Halt Verification Simulator (Paranoia Layer 0-2) */}
              <div className="p-4 rounded-2xl bg-muted/20 border border-border/50 space-y-3">
                <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <PlayCircle size={14} className="text-sky-400" />
                  Live Auto-Halt Verification Simulator
                </h4>
                <p className="text-[11px] text-muted-foreground">
                  Simulate an incoming booking webhook payload to prove that outreach stops immediately for the prospect.
                </p>

                <div className="flex flex-col sm:flex-row gap-2">
                  <select
                    value={bookingPlatform}
                    onChange={(e: any) => setBookingPlatform(e.target.value)}
                    className="bg-background border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none"
                  >
                    <option value="calendly">Calendly (invitee.created)</option>
                    <option value="calcom">Cal.com (BOOKING_CREATED)</option>
                    <option value="hubspot">HubSpot Meetings</option>
                  </select>

                  <input
                    type="email"
                    value={testBookingEmail}
                    onChange={(e) => setTestBookingEmail(e.target.value)}
                    placeholder="prospect@enterprise.com"
                    className="flex-1 bg-background border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none"
                  />

                  <button
                    onClick={handleSimulateBooking}
                    disabled={isTestingBooking}
                    className="px-3.5 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-xs shrink-0 cursor-pointer"
                  >
                    {isTestingBooking ? "Testing..." : "Simulate Booking"}
                  </button>
                </div>

                {bookingTestResult && (
                  <div className={`p-3 rounded-xl text-xs font-mono ${
                    bookingTestResult.status === "success" 
                      ? "bg-emerald-950/30 border border-emerald-500/30 text-emerald-300"
                      : "bg-amber-950/30 border border-amber-500/30 text-amber-300"
                  }`}>
                    {bookingTestResult.status === "success" ? (
                      <div className="space-y-1">
                        <div className="font-bold flex items-center gap-1 text-emerald-400">
                          <CheckCircle2 size={13} /> Sequence Halted Successfully!
                        </div>
                        <div>Lead ID: {bookingTestResult.lead_id}</div>
                        <div>Status: Meeting Booked (Active in-flight tasks cancelled)</div>
                      </div>
                    ) : (
                      <div>
                        Status: Ignored ({bookingTestResult.reason})
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Setup steps */}
              <div className="p-4 rounded-2xl bg-muted/20 border border-border/50 space-y-3">
                <h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
                  Quick 3-Step Setup
                </h4>
                <ol className="text-xs text-muted-foreground space-y-2 list-decimal list-inside leading-relaxed">
                  <li>
                    <strong className="text-foreground">Calendly:</strong> Go to <em>Integrations & apps</em> &rarr; <em>Webhooks</em> &rarr; <em>Add Webhook</em> and paste the URL above with event <code>invitee.created</code>.
                  </li>
                  <li>
                    <strong className="text-foreground">Cal.com:</strong> Go to <em>Settings</em> &rarr; <em>Webhooks</em> &rarr; <em>New Webhook</em> and paste the URL above with event <code>BOOKING_CREATED</code>.
                  </li>
                  <li>
                    <strong className="text-foreground">HubSpot Meetings:</strong> Set up a workflow webhook trigger on meeting activity.
                  </li>
                </ol>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={() => setShowCalendlyModal(false)}
                  className="px-6 py-2.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold transition-all cursor-pointer shadow-sm"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── API Keys & Developer Tokens Vault Modal (Paranoia Layer 0-2) ── */}
      {showApiKeysModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/85 backdrop-blur-md">
          <div className="bg-card w-full max-w-3xl rounded-3xl border border-blue-500/20 shadow-2xl p-6 sm:p-8 relative max-h-[92vh] overflow-y-auto">
            <button 
              onClick={() => {
                setShowApiKeysModal(false);
                setVaultGeneratedKey(null);
                setKeyToRevoke(null);
              }}
              className="absolute top-6 right-6 p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
            >
              <X size={20} />
            </button>

            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
                <Key size={24} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
                  API Key & Access Token Vault
                  <ShieldCheck size={16} className="text-blue-400" />
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Manage cryptographically hashed SHA-256 tokens for external agents, MCP, and inbound webhook pipelines.
                </p>
              </div>
            </div>

            <div className="space-y-6">
              {/* Generate New Key Box */}
              <div className="p-5 rounded-2xl border border-border/60 bg-background/50 space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Sparkles size={13} className="text-amber-400" />
                    Issue New Scoped API Key
                  </h4>
                  {!isPro && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                      <Lock size={10} /> Pro Required
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-semibold text-muted-foreground block mb-1">
                      Key Description / Client Name
                    </label>
                    <input
                      type="text"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder="e.g. Cursor MCP, Apollo Webhook Cron"
                      className="w-full bg-muted/30 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:border-blue-500/50"
                    />
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-muted-foreground block mb-1">
                      Allowed RBAC Scopes
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {[
                        "campaigns:read", "campaigns:write", "leads:read", "leads:write", "browser:execute"
                      ].map((scope) => {
                        const isSelected = selectedScopes.includes(scope);
                        return (
                          <button
                            key={scope}
                            type="button"
                            onClick={() => {
                              if (isSelected) {
                                setSelectedScopes(selectedScopes.filter(s => s !== scope));
                              } else {
                                setSelectedScopes([...selectedScopes, scope]);
                              }
                            }}
                            className={`px-2 py-1 rounded-lg text-[10px] font-mono transition-all cursor-pointer ${
                              isSelected
                                ? "bg-blue-600 text-white font-bold"
                                : "bg-muted/40 text-muted-foreground border border-border/40"
                            }`}
                          >
                            <span className="inline-flex items-center gap-1.5">
                              {isSelected && <Check size={12} className="shrink-0" />}
                              <span>{scope}</span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="flex justify-end pt-1">
                  <button
                    onClick={handleCreateVaultKey}
                    disabled={isCreatingVaultKey || !newKeyName.trim()}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-xs cursor-pointer flex items-center gap-1.5"
                  >
                    {isCreatingVaultKey ? (
                      <>
                        <RefreshCw size={12} className="animate-spin" />
                        <span>Generating...</span>
                      </>
                    ) : (
                      <>
                        <Key size={12} />
                        <span>Issue Scoped Key</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Newly Generated Key Alert Box */}
                {vaultGeneratedKey && (
                  <div className="p-4 rounded-2xl bg-amber-950/30 border border-amber-500/30 space-y-2">
                    <div className="flex items-center gap-1.5 text-amber-300 text-xs font-bold">
                      <AlertTriangle size={14} /> One-Time Secret Key Token Display
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      Copy this token now. It is cryptographically hashed with SHA-256 and will never be displayed again:
                    </p>
                    <div className="flex items-center gap-2 bg-black/40 p-2.5 rounded-xl border border-amber-500/30 font-mono text-xs">
                      <span className="flex-1 truncate text-amber-200">{vaultGeneratedKey}</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(vaultGeneratedKey);
                          setCopiedVaultKey(true);
                          toast.success("API key copied to clipboard!");
                          setTimeout(() => setCopiedVaultKey(false), 2000);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 text-xs flex items-center gap-1 font-sans font-semibold cursor-pointer shrink-0"
                      >
                        {copiedVaultKey ? <Check size={12} /> : <Copy size={12} />}
                        {copiedVaultKey ? "Copied" : "Copy Token"}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Active Keys Table */}
              <div className="p-4 rounded-2xl bg-muted/20 border border-border/50 space-y-3">
                <h4 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center justify-between">
                  <span>Registered Workspace Keys</span>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    {apiKeysData?.data?.length || 0} Total
                  </span>
                </h4>

                {(!apiKeysData?.data || apiKeysData.data.length === 0) ? (
                  <div className="text-xs text-muted-foreground text-center py-6">
                    No API keys have been issued for this workspace yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {apiKeysData.data.map((key: any) => (
                      <div
                        key={key.id}
                        className={`p-3 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                          key.is_active
                            ? "bg-background/60 border-border/60"
                            : "bg-muted/10 border-border/30 opacity-60"
                        }`}
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-foreground">{key.name}</span>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                              key.is_active
                                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                                : "bg-muted text-muted-foreground"
                            }`}>
                              {key.is_active ? "Active" : "Revoked"}
                            </span>
                          </div>

                          <div className="flex items-center gap-3 text-[11px] font-mono text-muted-foreground">
                            <span>Prefix: {key.key_prefix}••••••••</span>
                            <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                          </div>

                          <div className="flex flex-wrap gap-1 mt-1">
                            {(key.scopes || []).map((s: string) => (
                              <span key={s} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground">
                                {s}
                              </span>
                            ))}
                          </div>
                        </div>

                        {key.is_active && (
                          <div className="shrink-0">
                            {keyToRevoke === key.id ? (
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleRevokeKey(key.id)}
                                  disabled={isRevokingKey}
                                  className="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-[11px] font-bold cursor-pointer"
                                >
                                  {isRevokingKey ? "Revoking..." : "Confirm Revoke"}
                                </button>
                                <button
                                  onClick={() => setKeyToRevoke(null)}
                                  className="px-2 py-1 bg-muted hover:bg-muted/80 text-foreground rounded-lg text-[11px] cursor-pointer"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setKeyToRevoke(key.id)}
                                className="px-2.5 py-1 bg-muted/40 hover:bg-rose-500/10 hover:text-rose-400 text-muted-foreground rounded-lg text-[11px] font-semibold border border-border/40 transition-colors cursor-pointer flex items-center gap-1"
                              >
                                <Trash2 size={12} />
                                <span>Revoke</span>
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={() => setShowApiKeysModal(false)}
                  className="px-6 py-2.5 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-bold transition-all cursor-pointer"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal 6: Outbound Webhook Streaming & Observability (Layer 0, 1, 2) ── */}
      {showOutboundWebhooksModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md">
          <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-card border border-border/80 rounded-3xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-border/60 bg-muted/20">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-emerald-500/20 via-teal-500/20 to-indigo-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <Radio size={20} className="animate-pulse" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-foreground">Visual Webhook Studio & Automation Hub</h2>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
                      HMAC-SHA256 Encrypted
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold">
                      Live Delivery Replay
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Bi-directional webhook streaming, HMAC signature verification, and Zapier / Make schema mapping.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setShowOutboundWebhooksModal(false);
                  setNewlyCreatedSecret(null);
                  setObservabilityEndpointId(null);
                }}
                className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-xl transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            {/* Tab Bar */}
            <div className="flex items-center gap-1 px-6 pt-2 border-b border-border/60 bg-muted/10 shrink-0">
              <button
                onClick={() => setWebhookStudioTab("endpoints")}
                className={`pb-2.5 px-3.5 text-xs font-bold border-b-2 transition-all flex items-center gap-1.5 cursor-pointer ${
                  webhookStudioTab === "endpoints"
                    ? "border-emerald-500 text-emerald-400"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <Radio size={13} />
                <span>Endpoints & Deliveries</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-muted font-mono">
                  {(webhooksData?.data || []).length}
                </span>
              </button>

              <button
                onClick={() => setWebhookStudioTab("verifier")}
                className={`pb-2.5 px-3.5 text-xs font-bold border-b-2 transition-all flex items-center gap-1.5 cursor-pointer ${
                  webhookStudioTab === "verifier"
                    ? "border-indigo-500 text-indigo-400"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <ShieldCheck size={13} />
                <span>HMAC Signature Verifier</span>
              </button>

              <button
                onClick={() => setWebhookStudioTab("schemas")}
                className={`pb-2.5 px-3.5 text-xs font-bold border-b-2 transition-all flex items-center gap-1.5 cursor-pointer ${
                  webhookStudioTab === "schemas"
                    ? "border-amber-500 text-amber-400"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <Zap size={13} />
                <span>Zapier & Make Schemas</span>
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">

              {/* ── TAB 1: Endpoints & Deliveries Observability ── */}
              {webhookStudioTab === "endpoints" && (
                <div className="space-y-6 animate-in fade-in">
                  {/* Newly Created Secret One-Time Banner */}
                  {newlyCreatedSecret && (
                    <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 space-y-2 animate-in fade-in slide-in-from-top-2">
                      <div className="flex items-center gap-2 text-amber-400 text-xs font-bold">
                        <ShieldCheck size={16} />
                        <span>Signing Secret Generated — Copy Now</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Ele-in encrypts webhook secrets at rest. This secret will <strong>never</strong> be displayed again. Use this secret to verify the <code className="font-mono text-foreground">EleIn-Signature</code> header.
                      </p>
                      <div className="flex items-center gap-2 bg-background/60 p-2.5 rounded-xl border border-amber-500/20 font-mono text-xs">
                        <span className="flex-1 truncate text-amber-300 font-semibold">{newlyCreatedSecret}</span>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(newlyCreatedSecret);
                            setCopiedNewSecret(true);
                            toast.success("Signing secret copied to clipboard!");
                            setTimeout(() => setCopiedNewSecret(false), 2000);
                          }}
                          className="px-3 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                        >
                          {copiedNewSecret ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                          <span>{copiedNewSecret ? "Copied!" : "Copy Secret"}</span>
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Endpoint Registration Form (Paranoia Layer 0 & 1) */}
                  <div className="p-5 rounded-2xl border border-border/70 bg-muted/20 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Plus size={16} className="text-emerald-400" />
                        <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Register New Endpoint</h3>
                      </div>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        Tier Quota: {(webhooksData?.data || []).length} / {tier === "ENTERPRISE" ? "50" : tier === "PRO" ? "10" : "0"} Endpoints
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-foreground">Destination Webhook URL</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="url"
                          placeholder="https://api.yourdomain.com/webhooks/elein or https://hooks.zapier.com/hooks/catch/..."
                          value={newWebhookUrl}
                          onChange={(e) => setNewWebhookUrl(e.target.value)}
                          className="flex-1 px-3.5 py-2 rounded-xl bg-background border border-border/80 text-foreground text-xs font-mono placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                        />
                        <button
                          onClick={handleCreateWebhookEndpoint}
                          disabled={isCreatingWebhook}
                          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl transition-all shadow-sm flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shrink-0"
                        >
                          {isCreatingWebhook ? (
                            <>
                              <RefreshCw size={13} className="animate-spin" />
                              <span>Registering...</span>
                            </>
                          ) : (
                            <>
                              <Plus size={13} />
                              <span>Add Endpoint</span>
                            </>
                          )}
                        </button>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Must be a publicly accessible HTTPS endpoint. Private IPs (127.0.0.1, 10.x, 192.168.x) are blocked by SSRF defense.
                      </p>
                    </div>

                    {/* Event Catalog Selection */}
                    <div className="space-y-2 pt-2 border-t border-border/40">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-medium text-foreground">Subscribed Events</label>
                        <div className="flex items-center gap-2 text-[11px]">
                          <button
                            onClick={() => setSelectedWebhookEvents(["*"])}
                            className="text-emerald-400 hover:underline font-semibold cursor-pointer"
                          >
                            All Events (*)
                          </button>
                          <span className="text-muted-foreground">|</span>
                          <button
                            onClick={() => setSelectedWebhookEvents([
                              "lead.connected", "lead.replied", "intent.hot_detected", "lead.meeting_booked"
                            ])}
                            className="text-muted-foreground hover:text-foreground cursor-pointer"
                          >
                            Core High-Intent Triggers
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {[
                          { id: "lead.connected", label: "lead.connected", desc: "LinkedIn accepted" },
                          { id: "lead.replied", label: "lead.replied", desc: "Prospect message reply" },
                          { id: "intent.hot_detected", label: "intent.hot_detected", desc: "Social Radar score >= 75" },
                          { id: "lead.meeting_booked", label: "lead.meeting_booked", desc: "Calendar booking" },
                          { id: "lead.email_discovered", label: "lead.email_discovered", desc: "Waterfall email match" },
                          { id: "lead.enrolled", label: "lead.enrolled", desc: "Intent enroll trigger" },
                          { id: "message.sent", label: "message.sent", desc: "LinkedIn dispatch" },
                          { id: "connection.sent", label: "connection.sent", desc: "Connection invite" },
                          { id: "campaign.completed", label: "campaign.completed", desc: "Sequence terminal node" },
                          { id: "*", label: "* (All Events)", desc: "Wildcard stream" }
                        ].map(ev => {
                          const isSelected = selectedWebhookEvents.includes(ev.id);
                          return (
                            <div
                              key={ev.id}
                              onClick={() => {
                                if (ev.id === "*") {
                                  setSelectedWebhookEvents(isSelected ? [] : ["*"]);
                                } else {
                                  const withoutWildcard = selectedWebhookEvents.filter(x => x !== "*");
                                  if (isSelected) {
                                    setSelectedWebhookEvents(withoutWildcard.filter(x => x !== ev.id));
                                  } else {
                                    setSelectedWebhookEvents([...withoutWildcard, ev.id]);
                                  }
                                }
                              }}
                              className={`p-2 rounded-xl border text-left cursor-pointer transition-all ${
                                isSelected
                                  ? "bg-emerald-500/10 border-emerald-500/40 text-foreground"
                                  : "bg-background/40 border-border/50 text-muted-foreground hover:bg-background/80"
                              }`}
                            >
                              <div className="flex items-center gap-1.5">
                                {isSelected ? (
                                  <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                                ) : (
                                  <div className="w-3.5 h-3.5 rounded border border-border/80 shrink-0" />
                                )}
                                <span className="text-[11px] font-mono font-semibold truncate">{ev.label}</span>
                              </div>
                              <p className="text-[10px] text-muted-foreground truncate mt-0.5 pl-5">{ev.desc}</p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Active Endpoints List */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
                        <Globe size={15} className="text-indigo-400" />
                        <span>Configured Endpoints ({(webhooksData?.data || []).length})</span>
                      </h3>
                      <button
                        onClick={() => mutateWebhooks()}
                        className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted/40 transition-colors cursor-pointer"
                        title="Refresh Endpoints"
                      >
                        <RefreshCw size={13} />
                      </button>
                    </div>

                    {(!webhooksData?.data || webhooksData.data.length === 0) ? (
                      <div className="p-8 text-center rounded-2xl border border-dashed border-border/60 bg-muted/10 space-y-2">
                        <Radio size={24} className="mx-auto text-muted-foreground/60" />
                        <p className="text-xs font-medium text-foreground">No Webhook Endpoints Configured</p>
                        <p className="text-[11px] text-muted-foreground max-w-sm mx-auto">
                          Add your first endpoint above or connect a Zapier / Make hook to begin streaming real-time LinkedIn and email pipeline events with signature verification.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {webhooksData.data.map((ep: any) => {
                          const isTesting = testingEndpointId === ep.id;
                          const testRes = testEndpointResults[ep.id];
                          const isObserving = observabilityEndpointId === ep.id;

                          return (
                            <div
                              key={ep.id}
                              className={`p-4 rounded-2xl border transition-all space-y-3 ${
                                ep.is_active
                                  ? "bg-background/80 border-border/80 shadow-sm"
                                  : "bg-muted/10 border-border/40 opacity-75"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="space-y-1 min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className={`w-2 h-2 rounded-full shrink-0 ${ep.is_active ? "bg-emerald-400 animate-pulse" : "bg-muted-foreground"}`} />
                                    <span className="text-xs font-mono font-bold text-foreground truncate">{ep.url}</span>
                                    <span className={`text-[10px] px-2 py-0.2 rounded-full font-bold ${
                                      ep.is_active
                                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                        : "bg-muted text-muted-foreground"
                                    }`}>
                                      {ep.is_active ? "Active" : "Disabled"}
                                    </span>
                                  </div>

                                  <div className="flex flex-wrap gap-1 mt-1.5">
                                    {(ep.event_types || []).map((t: string) => (
                                      <span key={t} className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-muted/60 text-muted-foreground border border-border/40">
                                        {t}
                                      </span>
                                    ))}
                                  </div>
                                </div>

                                {/* Endpoint Actions */}
                                <div className="flex items-center gap-1.5 shrink-0">
                                  <button
                                    onClick={() => handleTestWebhookPing(ep.id)}
                                    disabled={isTesting || !ep.is_active}
                                    className="px-2.5 py-1.5 bg-indigo-600/10 hover:bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                                    title="Send a signed test ping to verify latency and connectivity"
                                  >
                                    {isTesting ? (
                                      <RefreshCw size={12} className="animate-spin" />
                                    ) : (
                                      <PlayCircle size={12} />
                                    )}
                                    <span>{isTesting ? "Pinging..." : "Test Ping"}</span>
                                  </button>

                                  <button
                                    onClick={() => setObservabilityEndpointId(isObserving ? null : ep.id)}
                                    className={`px-2.5 py-1.5 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 cursor-pointer ${
                                      isObserving
                                        ? "bg-foreground text-background border-foreground"
                                        : "bg-muted/40 hover:bg-muted text-foreground border-border/60"
                                    }`}
                                    title="View recent delivery attempts and status history"
                                  >
                                    <Activity size={12} />
                                    <span>{isObserving ? "Hide History" : "Deliveries"}</span>
                                  </button>

                                  <button
                                    onClick={() => handleToggleWebhookActive(ep)}
                                    className="p-1.5 text-muted-foreground hover:text-foreground rounded-xl hover:bg-muted/40 transition-colors cursor-pointer"
                                    title={ep.is_active ? "Disable Endpoint" : "Activate Endpoint"}
                                  >
                                    <Radio size={14} className={ep.is_active ? "text-emerald-400" : "text-muted-foreground"} />
                                  </button>

                                  {endpointToDelete === ep.id ? (
                                    <div className="flex items-center gap-1">
                                      <button
                                        onClick={() => handleDeleteWebhookEndpoint(ep.id)}
                                        disabled={isDeletingEndpoint}
                                        className="px-2 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-[10px] font-bold cursor-pointer"
                                      >
                                        Confirm
                                      </button>
                                      <button
                                        onClick={() => setEndpointToDelete(null)}
                                        className="px-1.5 py-1 bg-muted text-muted-foreground rounded-lg text-[10px] cursor-pointer"
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  ) : (
                                    <button
                                      onClick={() => setEndpointToDelete(ep.id)}
                                      className="p-1.5 text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 rounded-xl transition-colors cursor-pointer"
                                      title="Delete Webhook"
                                    >
                                      <Trash2 size={14} />
                                    </button>
                                  )}
                                </div>
                              </div>

                              {/* Live Diagnostic Test Result Card */}
                              {testRes && (
                                <div className="p-3 rounded-xl bg-muted/30 border border-border/50 text-xs space-y-2 animate-in fade-in">
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <span className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${
                                        testRes.status === "success"
                                          ? "bg-emerald-500/20 text-emerald-400"
                                          : "bg-rose-500/20 text-rose-400"
                                      }`}>
                                        HTTP {testRes.status_code || "ERR"}
                                      </span>
                                      <span className="font-mono text-muted-foreground text-[11px]">
                                        ⏱ Latency: <strong className="text-foreground">{testRes.latency_ms}ms</strong>
                                      </span>
                                    </div>
                                    <span className="text-[10px] text-muted-foreground font-mono">
                                      Signature: {testRes.signature_header}
                                    </span>
                                  </div>
                                  <pre className="p-2 rounded-lg bg-slate-950 text-slate-300 font-mono text-[11px] overflow-x-auto truncate">
                                    {testRes.response_body || "(Empty response body)"}
                                  </pre>
                                </div>
                              )}

                              {/* Observability Deliveries Drawer with Live Replay */}
                              {isObserving && (
                                <div className="p-4 rounded-xl bg-muted/20 border border-border/60 space-y-3 animate-in fade-in">
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                                      <Activity size={13} className="text-emerald-400" />
                                      Recent Deliveries Observability
                                    </span>
                                    <button
                                      onClick={() => mutateDeliveries()}
                                      className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 cursor-pointer"
                                    >
                                      <RefreshCw size={11} />
                                      <span>Refresh</span>
                                    </button>
                                  </div>

                                  {(!endpointDeliveriesData?.data || endpointDeliveriesData.data.length === 0) ? (
                                    <p className="text-[11px] text-muted-foreground py-2">
                                      No deliveries recorded yet. Fire a test ping or trigger a campaign action to inspect live transmission logs.
                                    </p>
                                  ) : (
                                    <div className="space-y-1.5 max-h-56 overflow-y-auto">
                                      {endpointDeliveriesData.data.map((d: any) => {
                                        const isReplaying = replayingDeliveryId === d.id;
                                        return (
                                          <div
                                            key={d.id}
                                            className="flex items-center justify-between p-2 rounded-lg bg-background/60 border border-border/40 text-[11px] font-mono gap-2"
                                          >
                                            <div className="flex items-center gap-2 truncate min-w-0">
                                              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                                d.delivery_status === "success" ? "bg-emerald-400" : d.delivery_status === "pending" ? "bg-amber-400" : "bg-rose-400"
                                              }`} />
                                              <span className="font-bold text-foreground shrink-0">{d.event_type}</span>
                                              <span className="text-muted-foreground shrink-0">({d.status_code || "---"})</span>
                                              <span className="text-muted-foreground text-[10px] truncate">{d.response_body || "(empty response)"}</span>
                                            </div>
                                            <div className="flex items-center gap-2 text-muted-foreground text-[10px] shrink-0">
                                              <span>Try #{d.attempt_count}</span>
                                              <span>{new Date(d.created_at).toLocaleTimeString()}</span>
                                              <button
                                                onClick={() => handleReplayDelivery(d.id)}
                                                disabled={isReplaying}
                                                className="px-2 py-0.5 rounded bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 hover:text-indigo-300 border border-indigo-500/30 font-semibold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50"
                                                title="Re-sign payload and replay delivery"
                                              >
                                                <RotateCcw size={10} className={isReplaying ? "animate-spin" : ""} />
                                                <span>{isReplaying ? "Replaying..." : "Replay"}</span>
                                              </button>
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── TAB 2: HMAC-SHA256 Signature Diagnostic Verifier ── */}
              {webhookStudioTab === "verifier" && (
                <div className="space-y-6 animate-in fade-in">
                  <div className="p-5 rounded-2xl border border-indigo-500/30 bg-indigo-500/5 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <ShieldCheck size={18} className="text-indigo-400" />
                        <div>
                          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                            HMAC-SHA256 Diagnostic Signature Tool
                          </h3>
                          <p className="text-[11px] text-muted-foreground">
                            Test and troubleshoot your external webhook consumer's signature verification logic against Ele-in's cryptographic standard.
                          </p>
                        </div>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold">
                        Tolerance: 300s
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Signing Secret */}
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-medium text-foreground">Signing Secret</label>
                          {newlyCreatedSecret && (
                            <button
                              onClick={() => setVerifySecret(newlyCreatedSecret)}
                              className="text-[10px] text-indigo-400 hover:underline cursor-pointer"
                            >
                              Use New Secret
                            </button>
                          )}
                        </div>
                        <div className="relative">
                          <input
                            type={verifyShowSecret ? "text" : "password"}
                            placeholder="whsec_0123456789abcdef..."
                            value={verifySecret}
                            onChange={(e) => setVerifySecret(e.target.value)}
                            className="w-full pl-3.5 pr-10 py-2 rounded-xl bg-background border border-border/80 text-foreground text-xs font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                          <button
                            type="button"
                            onClick={() => setVerifyShowSecret(!verifyShowSecret)}
                            className="absolute right-3 top-2.5 text-muted-foreground hover:text-foreground cursor-pointer"
                          >
                            <Eye size={13} />
                          </button>
                        </div>
                      </div>

                      {/* Timestamp */}
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-medium text-foreground">EleIn-Timestamp Header (Unix)</label>
                          <button
                            onClick={() => setVerifyTimestamp(Math.floor(Date.now() / 1000).toString())}
                            className="text-[10px] text-indigo-400 hover:underline cursor-pointer"
                          >
                            Set Current Epoch
                          </button>
                        </div>
                        <input
                          type="text"
                          placeholder="1718000000"
                          value={verifyTimestamp}
                          onChange={(e) => setVerifyTimestamp(e.target.value)}
                          className="w-full px-3.5 py-2 rounded-xl bg-background border border-border/80 text-foreground text-xs font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        />
                      </div>
                    </div>

                    {/* Signature Header */}
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-foreground">EleIn-Signature Header Value</label>
                      <input
                        type="text"
                        placeholder="sha256=1a2b3c4d5e... or raw hex"
                        value={verifySignature}
                        onChange={(e) => setVerifySignature(e.target.value)}
                        className="w-full px-3.5 py-2 rounded-xl bg-background border border-border/80 text-foreground text-xs font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>

                    {/* Raw Payload */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-medium text-foreground">Raw Webhook Request Body (JSON)</label>
                        <span className="text-[10px] text-muted-foreground">Exact raw string received over HTTP</span>
                      </div>
                      <textarea
                        rows={6}
                        value={verifyPayload}
                        onChange={(e) => setVerifyPayload(e.target.value)}
                        className="w-full p-3 rounded-xl bg-slate-950 text-slate-200 border border-border/80 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
                      />
                    </div>

                    {/* Verify Action Button */}
                    <div className="flex items-center justify-between pt-2">
                      <button
                        onClick={handleVerifySignature}
                        disabled={isVerifyingSignature}
                        className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl transition-all shadow-sm flex items-center gap-2 disabled:opacity-50 cursor-pointer"
                      >
                        {isVerifyingSignature ? (
                          <>
                            <RefreshCw size={13} className="animate-spin" />
                            <span>Verifying Cryptographic Digest...</span>
                          </>
                        ) : (
                          <>
                            <ShieldCheck size={14} />
                            <span>Run Diagnostic Signature Verification</span>
                          </>
                        )}
                      </button>

                      <span className="text-[11px] text-muted-foreground font-mono">
                        Algorithm: HMAC-SHA256 (Constant-Time Compare)
                      </span>
                    </div>

                    {/* Diagnostic Result Output */}
                    {signatureVerifyResult && (
                      <div className={`p-4 rounded-xl border space-y-2 animate-in fade-in ${
                        signatureVerifyResult.is_valid
                          ? "bg-emerald-500/10 border-emerald-500/30"
                          : "bg-rose-500/10 border-rose-500/30"
                      }`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {signatureVerifyResult.is_valid ? (
                              <CheckCircle2 size={16} className="text-emerald-400" />
                            ) : (
                              <AlertTriangle size={16} className="text-rose-400" />
                            )}
                            <span className={`text-xs font-bold font-mono ${
                              signatureVerifyResult.is_valid ? "text-emerald-400" : "text-rose-400"
                            }`}>
                              {signatureVerifyResult.is_valid ? "SIGNATURE VERIFICATION PASSED" : "SIGNATURE VERIFICATION FAILED"}
                            </span>
                          </div>
                          {signatureVerifyResult.drift_seconds !== undefined && (
                            <span className="text-[10px] font-mono text-muted-foreground">
                              Replay Drift: {signatureVerifyResult.drift_seconds}s
                            </span>
                          )}
                        </div>

                        {signatureVerifyResult.reason && (
                          <p className="text-xs text-foreground font-medium">
                            {signatureVerifyResult.reason}
                          </p>
                        )}

                        <div className="space-y-1 text-[11px] font-mono pt-1">
                          <div className="flex items-center gap-2">
                            <span className="text-muted-foreground w-20">Computed:</span>
                            <span className="text-foreground truncate">{signatureVerifyResult.computed_signature || "N/A"}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-muted-foreground w-20">Provided:</span>
                            <span className="text-foreground truncate">{signatureVerifyResult.provided_signature || "N/A"}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Reference Verification Implementation */}
                  <div className="p-4 rounded-2xl border border-border/60 bg-muted/10 space-y-2">
                    <div className="flex items-center gap-2">
                      <Code2 size={15} className="text-indigo-400" />
                      <h4 className="text-xs font-bold text-foreground">Verified Consumer Code Snippets</h4>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Compute <code className="font-mono text-foreground">HMAC-SHA256(timestamp + "." + raw_body, signing_secret)</code> and compare in constant time to prevent replay and timing attacks.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                      <div>
                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Node.js / Express</span>
                        <pre className="p-2.5 rounded-xl bg-slate-950 text-slate-200 text-[10px] font-mono overflow-x-auto mt-1 border border-border/30">
{`const crypto = require('crypto');
const signature = req.headers['elein-signature'];
const timestamp = req.headers['elein-timestamp'];
const payload = timestamp + '.' + req.rawBody;
const expected = crypto.createHmac('sha256', secret)
  .update(payload).digest('hex');
const valid = crypto.timingSafeEqual(
  Buffer.from(signature.replace('sha256=', '')), 
  Buffer.from(expected)
);`}
                        </pre>
                      </div>

                      <div>
                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Python / FastAPI</span>
                        <pre className="p-2.5 rounded-xl bg-slate-950 text-slate-200 text-[10px] font-mono overflow-x-auto mt-1 border border-border/30">
{`import hmac, hashlib
sig = request.headers.get("elein-signature", "").removeprefix("sha256=")
ts = request.headers.get("elein-timestamp")
body_bytes = await request.body()
payload = f"{ts}.".encode() + body_bytes
expected = hmac.new(
  secret.encode(), payload, hashlib.sha256
).hexdigest()
valid = hmac.compare_digest(sig, expected)`}
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* ── TAB 3: Zapier, Make.com, & HubSpot Workflow Automation Hub ── */}
              {webhookStudioTab === "schemas" && (
                <div className="space-y-6 animate-in fade-in">
                  <div className="p-5 rounded-2xl border border-amber-500/30 bg-amber-500/5 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Zap size={18} className="text-amber-400" />
                        <div>
                          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                            Zapier & Make Automation Workflow Schemas
                          </h3>
                          <p className="text-[11px] text-muted-foreground">
                            Instantly trigger Zaps, Make scenarios, and HubSpot CRM workflows when prospects reply, book meetings, or register hot buying intent.
                          </p>
                        </div>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold">
                        REST Hook Schema
                      </span>
                    </div>

                    {/* Event Selector Chips */}
                    <div className="space-y-2">
                      <label className="text-xs font-medium text-foreground">Select Trigger Event</label>
                      <div className="flex flex-wrap gap-2">
                        {[
                          { id: "lead.replied", label: "lead.replied", badge: "Response Detected" },
                          { id: "intent.hot_detected", label: "intent.hot_detected", badge: "Social Radar Hot" },
                          { id: "lead.meeting_booked", label: "lead.meeting_booked", badge: "Calendar Booking" },
                          { id: "lead.connected", label: "lead.connected", badge: "Invite Accepted" },
                          { id: "lead.email_discovered", label: "lead.email_discovered", badge: "Waterfall Match" },
                          { id: "lead.enrolled", label: "lead.enrolled", badge: "Campaign Enroll" },
                          { id: "message.sent", label: "message.sent", desc: "Outreach Dispatched" }
                        ].map(ev => {
                          const isSelected = schemaEventType === ev.id;
                          return (
                            <button
                              key={ev.id}
                              onClick={() => setSchemaEventType(ev.id)}
                              className={`px-3 py-1.5 rounded-xl text-xs font-mono font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                                isSelected
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/50 shadow-sm"
                                  : "bg-muted/40 hover:bg-muted text-muted-foreground border border-border/50"
                              }`}
                            >
                              <span>{ev.label}</span>
                              <span className="text-[9px] px-1 py-0.2 rounded bg-background/60 opacity-80 font-sans">
                                {ev.badge}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* JSON Schema Sample Preview */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-medium text-foreground">
                          Sample Payload for Zapier "Test Trigger" Step ({schemaEventType})
                        </label>
                        <button
                          onClick={() => {
                            const jsonStr = JSON.stringify(sampleSchemaData?.sample || {}, null, 2);
                            navigator.clipboard.writeText(jsonStr);
                            setCopiedSampleJson(true);
                            toast.success("Sample JSON schema copied for Zapier / Make!");
                            setTimeout(() => setCopiedSampleJson(false), 2000);
                          }}
                          className="px-3 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                        >
                          {copiedSampleJson ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                          <span>{copiedSampleJson ? "Copied!" : "Copy Sample JSON"}</span>
                        </button>
                      </div>

                      <pre className="p-4 rounded-xl bg-slate-950 text-amber-100/90 font-mono text-xs max-h-72 overflow-y-auto border border-border/80">
                        {isLoadingSample
                          ? "// Loading realistic event schema..."
                          : JSON.stringify(sampleSchemaData?.sample || {}, null, 2)}
                      </pre>
                    </div>

                    {/* 3-Step Zapier / Make Connection Guide */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-border/40">
                      <div className="p-3 rounded-xl bg-background/60 border border-border/50 space-y-1">
                        <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">Step 1: Create Catch Hook</span>
                        <p className="text-xs text-muted-foreground">
                          In Zapier, choose <strong>Webhooks by Zapier</strong> with event <strong>Catch Hook</strong>. In Make, add a <strong>Custom Webhook</strong> module.
                        </p>
                      </div>

                      <div className="p-3 rounded-xl bg-background/60 border border-border/50 space-y-1">
                        <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">Step 2: Register in Ele-in</span>
                        <p className="text-xs text-muted-foreground">
                          Paste your Zapier / Make webhook URL into the <strong>Endpoints & Deliveries</strong> tab and select the events you want to stream.
                        </p>
                      </div>

                      <div className="p-3 rounded-xl bg-background/60 border border-border/50 space-y-1">
                        <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">Step 3: Test & Map Fields</span>
                        <p className="text-xs text-muted-foreground">
                          Use the sample JSON above or hit <strong>Test Ping</strong> to auto-populate fields like <code className="text-foreground">lead_name</code> and <code className="text-foreground">intent_score</code> in Slack or CRM.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Close Button */}
              <div className="flex justify-end pt-2">
                <button
                  onClick={() => {
                    setShowOutboundWebhooksModal(false);
                    setNewlyCreatedSecret(null);
                    setObservabilityEndpointId(null);
                  }}
                  className="px-6 py-2.5 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-bold transition-all cursor-pointer"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
