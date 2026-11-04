import { useState, useMemo, useRef } from "react";
import useSWR from "swr";
import { motion, AnimatePresence } from "motion/react";
import {
  Ban,
  Globe,
  Mail,
  Plus,
  Trash2,
  Search,
  Download,
  Upload,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  ShieldAlert,
  ShieldCheck,
  Loader2,
  FileSpreadsheet,
  X,
  RefreshCw,
  Info
} from "lucide-react";
import { Linkedin } from "@/components/icons/Linkedin";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";
import Papa from "papaparse";

import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";

interface SuppressionEntry {
  id: string;
  workspace_id: string;
  value?: string;
  email?: string | null;
  domain?: string | null;
  linkedin_url?: string | null;
  reason?: string;
  created_at: string;
}

interface SuppressionResponse {
  status: string;
  data: SuppressionEntry[];
  total: number;
  limit: number;
  offset: number;
}

const PUBLIC_FREEMAIL_DOMAINS = new Set([
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "yahoo.co.uk",
  "yahoo.co.in",
  "hotmail.com",
  "outlook.com",
  "live.com",
  "msn.com",
  "icloud.com",
  "me.com",
  "mac.com",
  "aol.com",
  "protonmail.com",
  "proton.me",
  "zoho.com",
  "gmx.com",
  "mail.com",
  "yandex.com",
]);

const REASON_OPTIONS = [
  { value: "manual_dnc", label: "Manual Do-Not-Contact", color: "bg-red-500/10 text-red-500 border-red-500/20" },
  { value: "competitor", label: "Competitor / Rival Firm", color: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
  { value: "existing_client", label: "Existing Client / Partner", color: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
  { value: "customer_request", label: "Prospect Requested Removal", color: "bg-rose-500/10 text-rose-500 border-rose-500/20" },
  { value: "legal_compliance", label: "Legal & Regulatory Exclusion", color: "bg-purple-500/10 text-purple-500 border-purple-500/20" },
  { value: "internal_domain", label: "Internal Company Domain", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
];

export function ExclusionsSettings({ workspaceId }: { workspaceId: string | null }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | "domain" | "email" | "linkedin">("all");
  
  // Single Add State
  const [inputValue, setInputValue] = useState("");
  const [selectedReason, setSelectedReason] = useState("manual_dnc");
  const [isAdding, setIsAdding] = useState(false);

  // Paranoia Layer 2: Freemail Warning Modal
  const [freemailWarning, setFreemailWarning] = useState<string | null>(null);
  const [pendingFreemailPayload, setPendingFreemailPayload] = useState<{ value: string; reason: string } | null>(null);

  // Unblock Confirmation Modal
  const [entryToDelete, setEntryToDelete] = useState<SuppressionEntry | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Multi-Select Batch Unblock State
  const [selectedEntryIds, setSelectedEntryIds] = useState<Set<string>>(new Set());
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);
  const [showBatchConfirmModal, setShowBatchConfirmModal] = useState(false);

  // Bulk CSV Upload State
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [isUploadingBulk, setIsUploadingBulk] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<{ current: number; total: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Copy feedback
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // SWR query string
  const queryUrl = workspaceId
    ? `/api/leads/suppression?workspace_id=${workspaceId}&limit=500${searchTerm ? `&search=${encodeURIComponent(searchTerm)}` : ""}${typeFilter !== "all" ? `&entry_type=${typeFilter}` : ""}`
    : null;

  const { data, mutate, isLoading, error } = useSWR<SuppressionResponse>(queryUrl, fetcher, {
    revalidateOnFocus: false,
  });

  const entries = data?.data || [];
  const totalCount = data?.total || 0;

  // Category stats
  const stats = useMemo(() => {
    let domains = 0;
    let emails = 0;
    let linkedin = 0;
    entries.forEach((e) => {
      if (e.domain) domains++;
      else if (e.email) emails++;
      else if (e.linkedin_url) linkedin++;
    });
    return { domains, emails, linkedin, total: totalCount };
  }, [entries, totalCount]);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
    toast.success("Copied to clipboard");
  };

  const getEntryTypeInfo = (entry: SuppressionEntry) => {
    if (entry.domain) {
      return { label: "Domain", icon: Globe, value: entry.domain, color: "text-blue-500", bg: "bg-blue-500/10" };
    }
    if (entry.email) {
      return { label: "Email", icon: Mail, value: entry.email, color: "text-emerald-500", bg: "bg-emerald-500/10" };
    }
    if (entry.linkedin_url) {
      return { label: "LinkedIn", icon: Linkedin, value: entry.linkedin_url, color: "text-sky-500", bg: "bg-sky-500/10" };
    }
    return { label: "Other", icon: Ban, value: entry.value || "Unknown", color: "text-muted-foreground", bg: "bg-muted" };
  };

  const getReasonBadge = (reason?: string) => {
    const found = REASON_OPTIONS.find((r) => r.value === reason);
    if (found) {
      return (
        <span className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${found.color}`}>
          {found.label}
        </span>
      );
    }
    return (
      <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full border bg-muted text-muted-foreground border-border">
        {reason || "Manual DNC"}
      </span>
    );
  };

  // Layer 0 & 2: Add Exclusion Single Entry
  const handleAddEntry = async (allowFreemail = false) => {
    if (!inputValue.trim() || !workspaceId) return;
    const cleanVal = inputValue.trim().toLowerCase();

    // Paranoia Layer 2: Detect accidental wildcard freemail suppression
    const domainCandidate = cleanVal.replace(/^[\*\s@]+/, "").split(":")[0].replace(/^www\./, "");
    if (!allowFreemail && PUBLIC_FREEMAIL_DOMAINS.has(domainCandidate) && !cleanVal.includes("@")) {
      setFreemailWarning(domainCandidate);
      setPendingFreemailPayload({ value: cleanVal, reason: selectedReason });
      return;
    }

    setIsAdding(true);
    try {
      const res = await fetchWithAuth("/api/leads/suppression", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          value: cleanVal,
          reason: selectedReason,
          allow_freemail_domain: allowFreemail,
          trigger_retroactive_purge: true,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Failed to add exclusion entry");
      }

      const result = await res.json();
      const halted = result.purge_stats?.halted_states_count || 0;
      if (halted > 0) {
        toast.success(`Exclusion activated. Automatically halted ${halted} active campaign outreach touchpoints.`);
      } else {
        toast.success(`Added ${cleanVal} to workspace exclusion list.`);
      }

      setInputValue("");
      setFreemailWarning(null);
      setPendingFreemailPayload(null);
      mutate();
    } catch (err: any) {
      toast.error(err.message || "Failed to add exclusion entry");
    } finally {
      setIsAdding(false);
    }
  };

  // Layer 0: Delete / Unblock Entry
  const handleDeleteEntry = async () => {
    if (!entryToDelete || !workspaceId) return;
    setIsDeleting(true);
    try {
      const res = await fetchWithAuth(`/api/leads/suppression/${entryToDelete.id}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Failed to remove exclusion entry");
      }

      toast.success(`Removed ${entryToDelete.domain || entryToDelete.email || entryToDelete.value} from exclusions.`);
      setEntryToDelete(null);
      mutate();
    } catch (err: any) {
      toast.error(err.message || "Failed to remove exclusion entry");
    } finally {
      setIsDeleting(false);
    }
  };

  // Layer 0 & 2: Multi-Select Batch Operations
  const isAllSelected = entries.length > 0 && entries.every((e) => selectedEntryIds.has(e.id));

  const handleToggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedEntryIds(new Set());
    } else {
      setSelectedEntryIds(new Set(entries.map((e) => e.id)));
    }
  };

  const handleToggleSelectEntry = (id: string) => {
    setSelectedEntryIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBatchDelete = async () => {
    if (selectedEntryIds.size === 0 || !workspaceId || isBatchDeleting) return;
    setIsBatchDeleting(true);
    try {
      const res = await fetchWithAuth(`/api/leads/suppression/batch-delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry_ids: Array.from(selectedEntryIds) }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Failed to batch remove exclusion entries");
      }

      const resData = await res.json().catch(() => ({}));
      toast.success(`Successfully unblocked ${resData.deleted_count || selectedEntryIds.size} target(s).`);
      setSelectedEntryIds(new Set());
      setShowBatchConfirmModal(false);
      mutate();
    } catch (err: any) {
      toast.error(err.message || "Failed to unblock selected entries");
    } finally {
      setIsBatchDeleting(false);
    }
  };

  // Layer 1: Bulk CSV File Processing
  const handleBulkCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !workspaceId) return;

    setIsUploadingBulk(true);
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: async (results) => {
        const rows = results.data as Record<string, string>[];
        if (!rows.length) {
          toast.error("Uploaded CSV file is empty.");
          setIsUploadingBulk(false);
          return;
        }

        const entriesToSubmit: { value: string; reason: string }[] = [];
        for (const row of rows) {
          const val =
            row.domain ||
            row.Domain ||
            row.email ||
            row.Email ||
            row.linkedin_url ||
            row.LinkedIn ||
            row.website ||
            row.Website ||
            row.company_domain ||
            row.value ||
            row.Value ||
            Object.values(row)[0];

          if (val && typeof val === "string" && val.trim()) {
            entriesToSubmit.push({
              value: val.trim(),
              reason: row.reason || row.Reason || "bulk_import",
            });
          }
        }

        if (!entriesToSubmit.length) {
          toast.error("No valid domains or emails found in CSV headers.");
          setIsUploadingBulk(false);
          return;
        }

        try {
          const CHUNK = 500;
          let totalInserted = 0;
          let totalPurged = 0;

          for (let i = 0; i < entriesToSubmit.length; i += CHUNK) {
            const chunk = entriesToSubmit.slice(i, i + CHUNK);
            setBulkProgress({ current: Math.min(i + CHUNK, entriesToSubmit.length), total: entriesToSubmit.length });

            const res = await fetchWithAuth("/api/leads/suppression/bulk", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                entries: chunk,
                allow_freemail_domain: false,
                trigger_retroactive_purge: true,
              }),
            });

            if (res.ok) {
              const resData = await res.json();
              totalInserted += resData.inserted_count || 0;
              totalPurged += resData.purge_stats?.halted_states_count || 0;
            }
          }

          toast.success(
            `Import complete: ${totalInserted} exclusions added.${totalPurged > 0 ? ` ${totalPurged} active leads halted.` : ""}`
          );
          setIsBulkModalOpen(false);
          mutate();
        } catch (uploadErr: any) {
          toast.error(`Bulk import encountered an issue: ${uploadErr.message}`);
        } finally {
          setIsUploadingBulk(false);
          setBulkProgress(null);
          if (fileInputRef.current) fileInputRef.current.value = "";
        }
      },
      error: (csvErr) => {
        toast.error(`CSV Parsing error: ${csvErr.message}`);
        setIsUploadingBulk(false);
      },
    });
  };

  // Layer 1: Export Sanitized CSV
  const handleExportCsv = async () => {
    if (!workspaceId) return;
    try {
      const res = await fetchWithAuth("/api/leads/suppression/export");
      if (!res.ok) throw new Error("Failed to export suppression list");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `workspace_exclusions_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success("Exclusions list exported to CSV");
    } catch (err: any) {
      toast.error(err.message || "Failed to export exclusions");
    }
  };

  if (!workspaceId) {
    return (
      <EmptyState
        title="No Workspace Selected"
        description="Please select a workspace to view and manage its exclusion and DNC list."
        icon={Ban}
      />
    );
  }

  if (isLoading && !data) {
    return <SettingsLoadingSkeleton />;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-destructive/20 bg-destructive/5 rounded-2xl text-destructive text-center">
        <AlertTriangle className="h-10 w-10 mb-3" />
        <h3 className="font-semibold text-lg">Failed to Load Exclusion List</h3>
        <p className="text-sm opacity-80 mt-1 max-w-md">
          Unable to synchronize suppression records. Please verify your connection or refresh the page.
        </p>
        <button
          onClick={() => mutate()}
          className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-destructive text-destructive-foreground text-sm font-semibold hover:opacity-90 transition-all cursor-pointer"
        >
          <RefreshCw size={15} /> Retry Sync
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Total Exclusions</span>
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <ShieldCheck size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold tracking-tight text-foreground mt-2">{stats.total.toLocaleString()}</p>
          <span className="text-[11px] text-muted-foreground mt-0.5 block">Active DNC Protection</span>
        </div>

        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Blocked Domains</span>
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-500">
              <Globe size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold tracking-tight text-foreground mt-2">{stats.domains.toLocaleString()}</p>
          <span className="text-[11px] text-muted-foreground mt-0.5 block">Wildcard Company Shields</span>
        </div>

        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Blocked Emails</span>
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-500">
              <Mail size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold tracking-tight text-foreground mt-2">{stats.emails.toLocaleString()}</p>
          <span className="text-[11px] text-muted-foreground mt-0.5 block">Individual Opt-Outs</span>
        </div>

        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">LinkedIn Profiles</span>
            <div className="p-2 rounded-lg bg-sky-500/10 text-sky-500">
              <Linkedin size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold tracking-tight text-foreground mt-2">{stats.linkedin.toLocaleString()}</p>
          <span className="text-[11px] text-muted-foreground mt-0.5 block">Social Outreach Locks</span>
        </div>
      </div>

      {/* Main Control Card */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card shadow-sm space-y-6">
        <div>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
                <Ban size={20} className="text-destructive" />
                <span>Global Exclusions & Do-Not-Contact (DNC)</span>
              </h2>
              <p className="text-xs text-muted-foreground mt-1">
                Prevent outreach to specific competitors, existing clients, and opted-out contacts across all campaigns in this workspace.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsBulkModalOpen(true)}
                className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-all cursor-pointer"
              >
                <Upload size={14} /> Import CSV
              </button>
              <button
                type="button"
                onClick={handleExportCsv}
                className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-all cursor-pointer"
              >
                <Download size={14} /> Export CSV
              </button>
            </div>
          </div>
        </div>

        {/* Omni-Add Input Bar */}
        <div className="bg-background/50 p-4 rounded-xl border border-border/80 space-y-3">
          <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Plus size={14} className="text-primary" />
            <span>Add Single Exclusion</span>
          </label>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddEntry()}
                placeholder="Enter domain (competitor.com), email (lead@firm.com), or LinkedIn URL..."
                className="w-full px-3.5 py-2.5 text-xs rounded-lg border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              />
            </div>

            <select
              value={selectedReason}
              onChange={(e) => setSelectedReason(e.target.value)}
              className="px-3 py-2.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all cursor-pointer"
            >
              {REASON_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <button
              type="button"
              onClick={() => handleAddEntry()}
              disabled={isAdding || !inputValue.trim()}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm transition-all cursor-pointer"
            >
              {isAdding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              <span>Add Exclusion</span>
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
            <Info size={12} className="text-primary shrink-0" />
            <span>Domains automatically block all subdomains (e.g. adding <code>acme.com</code> suppresses <code>*@acme.com</code> and <code>*@corp.acme.com</code>).</span>
          </p>
        </div>

        {/* Search & Filter Toolbar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
          <div className="relative w-full sm:w-72">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search exclusions by value or reason..."
              className="w-full pl-9 pr-3.5 py-2 text-xs rounded-lg border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
            />
          </div>

          <div className="flex items-center gap-1.5 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
            <button
              type="button"
              onClick={() => setTypeFilter("all")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                typeFilter === "all"
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              All ({stats.total})
            </button>
            <button
              type="button"
              onClick={() => setTypeFilter("domain")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                typeFilter === "domain"
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              Domains ({stats.domains})
            </button>
            <button
              type="button"
              onClick={() => setTypeFilter("email")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                typeFilter === "email"
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              Emails ({stats.emails})
            </button>
            <button
              type="button"
              onClick={() => setTypeFilter("linkedin")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                typeFilter === "linkedin"
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              LinkedIn ({stats.linkedin})
            </button>
          </div>
        </div>

        {/* Exclusions Table */}
        <div className="border border-border rounded-xl overflow-hidden bg-background/50">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-muted-foreground font-semibold">
                  <th className="py-3 px-4 w-10">
                    <input
                      type="checkbox"
                      checked={isAllSelected}
                      onChange={handleToggleSelectAll}
                      className="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary cursor-pointer"
                      title="Select all exclusions on this page"
                    />
                  </th>
                  <th className="py-3 px-4">Exclusion Target</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Reason</th>
                  <th className="py-3 px-4">Added</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {entries.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <CheckCircle2 size={32} className="text-emerald-500/60" />
                        <p className="font-semibold text-foreground text-sm">No Exclusions Found</p>
                        <p className="text-xs text-muted-foreground max-w-sm">
                          {searchTerm
                            ? `No exclusion entries match "${searchTerm}".`
                            : "Your suppression list is clear. Add competitor domains or client emails above to shield them from outreach."}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  entries.map((entry) => {
                    const info = getEntryTypeInfo(entry);
                    const Icon = info.icon;
                    const displayVal = info.value;
                    const isCopied = copiedId === entry.id;
                    const isSelected = selectedEntryIds.has(entry.id);

                    return (
                      <tr key={entry.id} className={`transition-colors ${isSelected ? "bg-primary/5 hover:bg-primary/10" : "hover:bg-muted/20"}`}>
                        <td className="py-3.5 px-4 w-10">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleSelectEntry(entry.id)}
                            className="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary cursor-pointer"
                          />
                        </td>
                        <td className="py-3.5 px-4 font-medium text-foreground">
                          <div className="flex items-center gap-2 max-w-md">
                            <span className="truncate">{displayVal}</span>
                            <button
                              type="button"
                              onClick={() => handleCopy(entry.id, displayVal)}
                              className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors cursor-pointer"
                              title="Copy value"
                            >
                              {isCopied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                            </button>
                          </div>
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-semibold text-[11px] ${info.bg} ${info.color}`}>
                            <Icon size={12} />
                            {info.label}
                          </span>
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {getReasonBadge(entry.reason)}
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap text-muted-foreground text-[11px]">
                          {entry.created_at
                            ? formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })
                            : "Recently"}
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap text-right">
                          <button
                            type="button"
                            onClick={() => setEntryToDelete(entry)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold rounded-md text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
                            title="Unblock this exclusion"
                          >
                            <Trash2 size={12} />
                            <span>Unblock</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Paranoia Layer 2: Accidental Freemail Domain Warning Modal */}
      <AnimatePresence>
        {freemailWarning && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg p-6 rounded-2xl border border-amber-500/30 bg-card shadow-2xl relative"
            >
              <div className="flex items-start gap-4">
                <div className="p-3 rounded-xl bg-amber-500/10 text-amber-500 border border-amber-500/20 shrink-0">
                  <AlertTriangle size={24} />
                </div>
                <div className="space-y-2">
                  <h3 className="text-lg font-bold text-foreground">
                    Accidental Freemail Domain Shield
                  </h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    You are attempting to add <strong className="text-foreground font-mono">@{freemailWarning}</strong> to the global exclusion list.
                  </p>
                  <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-600 dark:text-amber-400">
                    <p className="font-semibold">Severe Outreach Blast Warning:</p>
                    <p className="mt-1">
                      Suppressing an entire public freemail provider will permanently halt and discard <strong>ALL personal email prospects</strong> across your entire workspace!
                    </p>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Did you mean to suppress a specific email address (e.g. <code>user@{freemailWarning}</code>) instead?
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => {
                    setFreemailWarning(null);
                    setPendingFreemailPayload(null);
                  }}
                  className="px-4 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-all cursor-pointer"
                >
                  Cancel & Fix Entry
                </button>
                <button
                  type="button"
                  onClick={() => handleAddEntry(true)}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-amber-500 text-white hover:bg-amber-600 shadow-sm transition-all cursor-pointer"
                >
                  Confirm Block Entire Provider
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Delete / Unblock Confirmation Modal */}
      <AnimatePresence>
        {entryToDelete && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 rounded-2xl border border-destructive/30 bg-card shadow-2xl relative"
            >
              <div className="flex items-start gap-4">
                <div className="p-3 rounded-xl bg-destructive/10 text-destructive border border-destructive/20 shrink-0">
                  <ShieldAlert size={24} />
                </div>
                <div className="space-y-2">
                  <h3 className="text-lg font-bold text-foreground">
                    Unblock Exclusion Target?
                  </h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    You are removing{" "}
                    <strong className="text-foreground font-mono">
                      {entryToDelete.domain || entryToDelete.email || entryToDelete.linkedin_url || entryToDelete.value}
                    </strong>{" "}
                    from the workspace exclusion list.
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Future and active campaigns will once again be permitted to enroll, enrich, and dispatch outreach to prospects under this target.
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setEntryToDelete(null)}
                  disabled={isDeleting}
                  className="px-4 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-all cursor-pointer"
                >
                  Keep Exclusion
                </button>
                <button
                  type="button"
                  onClick={handleDeleteEntry}
                  disabled={isDeleting}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm transition-all cursor-pointer"
                >
                  {isDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  <span>Unblock Target</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Bulk CSV Upload Modal */}
      <AnimatePresence>
        {isBulkModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg p-6 rounded-2xl border border-border bg-card shadow-2xl relative space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-lg bg-primary/10 text-primary">
                    <FileSpreadsheet size={18} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">Bulk CSV Exclusion Import</h3>
                    <p className="text-xs text-muted-foreground">Upload a CSV file of competitor domains or opt-out emails.</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setIsBulkModalOpen(false)}
                  disabled={isUploadingBulk}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-md transition-colors cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="space-y-3">
                <div className="p-4 rounded-xl border border-dashed border-border/80 bg-background/50 hover:bg-muted/20 transition-all text-center flex flex-col items-center justify-center gap-3">
                  <Upload size={32} className="text-muted-foreground" />
                  <div>
                    <p className="text-xs font-semibold text-foreground">Choose a CSV file to upload</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Auto-detects columns: <code>domain</code>, <code>email</code>, <code>website</code>, or <code>linkedin_url</code>.
                    </p>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,text/csv"
                    onChange={handleBulkCsvUpload}
                    disabled={isUploadingBulk}
                    className="text-xs text-muted-foreground file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 file:cursor-pointer cursor-pointer"
                  />
                </div>

                {isUploadingBulk && (
                  <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold text-primary">
                      <span className="flex items-center gap-2">
                        <Loader2 size={14} className="animate-spin" />
                        <span>Processing & retroactively purging in-flight leads...</span>
                      </span>
                      {bulkProgress && (
                        <span>
                          {bulkProgress.current} / {bulkProgress.total}
                        </span>
                      )}
                    </div>
                    {bulkProgress && (
                      <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-primary h-full transition-all duration-300"
                          style={{ width: `${Math.round((bulkProgress.current / bulkProgress.total) * 100)}%` }}
                        />
                      </div>
                    )}
                  </div>
                )}

                <div className="text-[11px] text-muted-foreground space-y-1 bg-muted/30 p-3 rounded-lg">
                  <p className="font-semibold text-foreground">CSV Import Notes:</p>
                  <ul className="list-disc list-inside space-y-0.5">
                    <li>Maximum 5,000 entries per CSV batch.</li>
                    <li>Duplicate entries are automatically filtered and deduped.</li>
                    <li>Retroactive purge automatically cancels any active campaign steps for matching contacts.</li>
                  </ul>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsBulkModalOpen(false)}
                  disabled={isUploadingBulk}
                  className="px-4 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-all cursor-pointer"
                >
                  Close
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Floating Batch Action Bar */}
      <AnimatePresence>
        {selectedEntryIds.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 30, scale: 0.95 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-foreground text-background px-5 py-3 rounded-2xl shadow-2xl border border-border/40 flex items-center gap-4"
          >
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              <span className="text-xs font-bold font-mono">
                {selectedEntryIds.size} {selectedEntryIds.size === 1 ? "target" : "targets"} selected
              </span>
            </div>

            <div className="h-4 w-px bg-background/20" />

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setSelectedEntryIds(new Set())}
                className="text-xs font-semibold text-background/70 hover:text-background transition-colors px-2 py-1 rounded-lg cursor-pointer"
              >
                Clear
              </button>

              <button
                type="button"
                onClick={() => setShowBatchConfirmModal(true)}
                className="px-3.5 py-1.5 bg-destructive hover:bg-destructive/90 text-white font-bold text-xs rounded-xl shadow-xs transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Trash2 size={13} />
                <span>Unblock Selected ({selectedEntryIds.size})</span>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Batch Unblock Confirmation Modal */}
      <AnimatePresence>
        {showBatchConfirmModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 rounded-2xl border border-border bg-card shadow-xl space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-destructive/10 text-destructive">
                  <AlertTriangle size={22} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-foreground">Confirm Batch Unblock</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Remove {selectedEntryIds.size} targets from workspace exclusion protection.
                  </p>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-muted/30 border border-border text-xs text-muted-foreground space-y-2">
                <p>
                  Removing these exclusions will permit cold outreach, automated LinkedIn connection requests, and campaign sequence steps to resume contacting matching leads.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowBatchConfirmModal(false)}
                  disabled={isBatchDeleting}
                  className="px-4 py-2 text-xs font-semibold rounded-xl border border-border hover:bg-muted text-foreground transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleBatchDelete}
                  disabled={isBatchDeleting}
                  className="px-5 py-2 text-xs font-semibold rounded-xl bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50 transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  {isBatchDeleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                  <span>Unblock {selectedEntryIds.size} Entries</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
