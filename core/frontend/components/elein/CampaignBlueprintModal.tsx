import React, { useState, useRef, useEffect, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import {
  X, Download, Upload, Copy, Check, FileJson, Shield, AlertTriangle,
  Sparkles, Layers, ArrowRight, RefreshCw, Palette, ExternalLink,
  Tag, Clock, MessageSquare, CheckCircle2, FileText, Undo2,
  History, Trash2, Camera, ShieldAlert, ShieldCheck, Mail, Sliders,
  BookmarkPlus, Search, Compass, Bookmark, Cloud, CloudUpload
} from "lucide-react"
import useSWR from "swr"
import { fetcher } from "@/lib/apiClient"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { useHRTreeStore, type SeqTreeNode, type StickyNote } from "@campaigns/eiTreeStore"
import {
  type EleInBlueprint,
  type EleInBlueprintMetadata,
  type BlueprintValidationResult,
  type ImportMode,
  type CanvasSnapshot,
  type VariableAuditItem,
  exportBlueprint,
  validateBlueprint,
  prepareImportNodes,
  downloadBlueprintFile,
  copyBlueprintToClipboard,
  parseBlueprintFile,
  parseBlueprintJsonString,
  calculateBlueprintStats,
  saveCanvasSnapshot,
  getCanvasSnapshots,
  restoreCanvasSnapshot,
  deleteCanvasSnapshot,
  clearCanvasSnapshots,
  auditBlueprintVariables,
  applyVariableFallbacksToTree,
  COMMON_SMART_FALLBACKS
} from "@/lib/blueprintSchema"
import {
  CURATED_BLUEPRINTS,
  getSavedWorkspaceBlueprints,
  saveBlueprintToWorkspaceLibrary,
  deleteBlueprintFromWorkspaceLibrary,
  saveBlueprintToCloud,
  deleteBlueprintFromCloud
} from "@/lib/blueprintGallery"

interface CampaignBlueprintModalProps {
  isOpen: boolean
  onClose: () => void
  initialTab?: "gallery" | "export" | "import" | "vault"
  preloadedBlueprint?: EleInBlueprint | null
}

export function CampaignBlueprintModal({
  isOpen,
  onClose,
  initialTab = "gallery",
  preloadedBlueprint = null,
}: CampaignBlueprintModalProps) {
  const [activeTab, setActiveTab] = useState<"gallery" | "export" | "import" | "vault">(initialTab)
  const rootNodes = useHRTreeStore(state => state.rootNodes)
  const stickyNotes = useHRTreeStore(state => state.stickyNotes)
  const formState = useHRTreeStore(state => state.formState)
  const loadTree = useHRTreeStore(state => state.loadTree)

  // ─── Gallery State ──────────────────────────────────────────────────────────
  const [galleryFilter, setGalleryFilter] = useState<string>("all")
  const [gallerySearch, setGallerySearch] = useState<string>("")
  const [savedBlueprints, setSavedBlueprints] = useState<EleInBlueprint[]>([])

  // ─── Export Form State ───────────────────────────────────────────────────────
  const [blueprintName, setBlueprintName] = useState("")
  const [blueprintDescription, setBlueprintDescription] = useState("")
  const [agencyName, setAgencyName] = useState("Ele-in Outbound Studio")
  const [authorName, setAuthorName] = useState("Campaign Architect")
  const [accentColor, setAccentColor] = useState("#6366f1")
  const [agencyWebsite, setAgencyWebsite] = useState("")
  const [sanitizeIds, setSanitizeIds] = useState(true)
  const [includeSticky, setIncludeSticky] = useState(true)
  const [isCopied, setIsCopied] = useState(false)
  const [isSavedToLibrary, setIsSavedToLibrary] = useState(false)
  const [isSavingToCloud, setIsSavingToCloud] = useState(false)
  const [isSavedToCloud, setIsSavedToCloud] = useState(false)

  // ─── Cloud Blueprints Sync ──────────────────────────────────────────────────
  const { data: cloudData, mutate: mutateCloud } = useSWR<any[]>("/api/elein/blueprints", fetcher, { revalidateOnFocus: true })

  const cloudBlueprints = useMemo<EleInBlueprint[]>(() => {
    if (!cloudData || !Array.isArray(cloudData)) return []
    return cloudData.map((r: any) => ({
      schema: r.schema_version || "elein-blueprint-v1",
      metadata: {
        id: r.id,
        name: r.name,
        description: r.description,
        version: r.version || "1.0.0",
        schemaVersion: r.schema_version || "elein-blueprint-v1",
        exportedAt: r.updated_at || r.created_at || new Date().toISOString(),
        branding: r.branding || {},
        tags: r.tags || ["cloud-synced"],
        stats: r.stats,
      },
      sequence: r.sequence_data || { rootNodes: [] },
    }))
  }, [cloudData])

  // ─── Import State ────────────────────────────────────────────────────────────
  const [importMode, setImportMode] = useState<ImportMode>("replace")
  const [importTab, setImportTab] = useState<"file" | "paste">("file")
  const [pastedJson, setPastedJson] = useState("")
  const [importedBlueprint, setImportedBlueprint] = useState<EleInBlueprint | null>(preloadedBlueprint)
  const [validationResult, setValidationResult] = useState<BlueprintValidationResult | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [isParsing, setIsParsing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // ─── Variable Reconciliation State ──────────────────────────────────────────
  const [fallbackOverrides, setFallbackOverrides] = useState<Record<string, string>>({})

  // ─── Rollback Vault State ────────────────────────────────────────────────────
  const [snapshots, setSnapshots] = useState<CanvasSnapshot[]>([])

  // ─── Accounts & Pre-Flight Check ───────────────────────────────────────────
  const { data: accounts } = useSWR<any[]>("/api/elein/accounts", fetcher, { revalidateOnFocus: false })

  const activeAccounts = useMemo(() => {
    if (!accounts || !Array.isArray(accounts)) return []
    return accounts.filter(
      (a: any) => a.id && a.is_active !== false && String(a.status || "").toUpperCase() !== "DISCONNECTED"
    )
  }, [accounts])

  const hasActiveLinkedIn = useMemo(() => {
    return activeAccounts.some(
      (a: any) => !a.channel || a.channel === "linkedin" || a.account_type === "linkedin"
    )
  }, [activeAccounts])

  const hasActiveEmail = useMemo(() => {
    return activeAccounts.some(
      (a: any) => a.channel === "email" || a.account_type === "email" || a.sender_pod_id
    )
  }, [activeAccounts])

  // Synchronize state on modal open
  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab)
      setBlueprintName(formState?.campaignName || "High-Impact Outbound Sequence")
      setSnapshots(getCanvasSnapshots())
      setSavedBlueprints(getSavedWorkspaceBlueprints())
      if (preloadedBlueprint) {
        setImportedBlueprint(preloadedBlueprint)
        setValidationResult(validateBlueprint(preloadedBlueprint))
        setActiveTab("import")
      }
    }
  }, [isOpen, initialTab, preloadedBlueprint, formState?.campaignName])

  // Refresh variable audit whenever importedBlueprint changes
  const variableAudit = useMemo(() => {
    if (!importedBlueprint?.sequence?.rootNodes) return []
    return auditBlueprintVariables(importedBlueprint.sequence.rootNodes)
  }, [importedBlueprint])

  // Initialize fallback overrides
  useEffect(() => {
    if (variableAudit.length > 0) {
      const initial: Record<string, string> = {}
      for (const item of variableAudit) {
        initial[item.name] = item.currentFallback || item.suggestedFallback || ""
      }
      setFallbackOverrides(initial)
    }
  }, [variableAudit])

  if (!isOpen) return null

  // Generated Blueprint Preview for Export
  const generatedExport = exportBlueprint(
    rootNodes,
    stickyNotes,
    {
      name: blueprintName,
      description: blueprintDescription,
      branding: {
        agencyName,
        authorName,
        accentColor,
        website: agencyWebsite,
        badge: "Verified Outbound Blueprint",
      },
      version: "1.0.0",
    },
    {
      sanitize: sanitizeIds,
      includeStickyNotes: includeSticky,
    }
  )

  const exportStats = generatedExport.metadata.stats || calculateBlueprintStats(rootNodes, stickyNotes)

  // ─── Handle File Import ────────────────────────────────────────────────────
  const handleFileSelected = async (file: File) => {
    setIsParsing(true)
    try {
      const blueprint = await parseBlueprintFile(file)
      const res = validateBlueprint(blueprint)
      setValidationResult(res)
      if (res.isValid) {
        setImportedBlueprint(blueprint)
        toast.success(`Loaded blueprint: "${blueprint.metadata.name}"`)
      } else {
        toast.error("Invalid blueprint structure", {
          description: res.errors[0] || "Unknown format issue",
        })
      }
    } catch (err: any) {
      toast.error("Failed to read blueprint file", {
        description: err.message || "File could not be parsed as JSON",
      })
    } finally {
      setIsParsing(false)
    }
  }

  const handleJsonPasteValidate = () => {
    if (!pastedJson.trim()) {
      toast.error("Please paste JSON blueprint text first.")
      return
    }
    try {
      const blueprint = parseBlueprintJsonString(pastedJson)
      const res = validateBlueprint(blueprint)
      setValidationResult(res)
      if (res.isValid) {
        setImportedBlueprint(blueprint)
        toast.success(`Validated blueprint: "${blueprint.metadata.name}"`)
      } else {
        toast.error("Validation error", {
          description: res.errors[0] || "Unknown format issue",
        })
      }
    } catch (err: any) {
      toast.error("Invalid JSON content", {
        description: err.message,
      })
    }
  }

  // ─── Apply Fallback Overrides to Blueprint ──────────────────────────────────
  const handleApplyFallbacks = () => {
    if (!importedBlueprint) return
    const updatedRoots = applyVariableFallbacksToTree(
      importedBlueprint.sequence.rootNodes,
      fallbackOverrides
    )
    const updatedBp: EleInBlueprint = {
      ...importedBlueprint,
      sequence: {
        ...importedBlueprint.sequence,
        rootNodes: updatedRoots,
      },
    }
    setImportedBlueprint(updatedBp)
    setValidationResult(validateBlueprint(updatedBp))
    toast.success("Applied smart fallbacks to sequence templates")
  }

  // ─── Execute Import from Modal ──────────────────────────────────────────────
  const handleConfirmImport = (targetBlueprint = importedBlueprint, mode = importMode) => {
    if (!targetBlueprint) return

    // 1. Layer 2 Paranoia: Automatically save canvas snapshot to rollback vault
    saveCanvasSnapshot(
      rootNodes,
      stickyNotes,
      `Pre-import: ${targetBlueprint.metadata.name || "Workflow Blueprint"}`
    )
    setSnapshots(getCanvasSnapshots())

    // Capture previous state for immediate in-toast Undo
    const previousRoots = [...rootNodes]
    const previousNotes = [...stickyNotes]

    const { nodes, stickyNotes: newNotes } = prepareImportNodes(
      targetBlueprint,
      rootNodes,
      stickyNotes,
      mode
    )

    loadTree(nodes, newNotes)
    onClose()

    toast.success(
      mode === "replace"
        ? `Replaced sequence with "${targetBlueprint.metadata.name}"`
        : `Appended "${targetBlueprint.metadata.name}" to sequence`,
      {
        description: `${nodes.length} total steps active on canvas. Snapshot saved to vault.`,
        action: {
          label: "Undo",
          onClick: () => {
            loadTree(previousRoots, previousNotes)
            toast.info("Import reverted back to previous canvas state.")
          },
        },
        duration: 9000,
      }
    )
  }

  // ─── Quick Load from Gallery ────────────────────────────────────────────────
  const handleInspectBlueprintFromGallery = (bp: EleInBlueprint) => {
    setImportedBlueprint(bp)
    setValidationResult(validateBlueprint(bp))
    setActiveTab("import")
    toast.info(`Inspecting "${bp.metadata.name}" in Import Hub`)
  }

  const handleDirectLoadFromGallery = (bp: EleInBlueprint) => {
    handleConfirmImport(bp, "replace")
  }

  // ─── Save Exported Blueprint to Library ─────────────────────────────────────
  const handleSaveToWorkspaceLibrary = () => {
    saveBlueprintToWorkspaceLibrary(generatedExport)
    setSavedBlueprints(getSavedWorkspaceBlueprints())
    setIsSavedToLibrary(true)
    toast.success(`Saved "${generatedExport.metadata.name}" to Workspace Blueprint Library`)
    setTimeout(() => setIsSavedToLibrary(false), 3000)
  }

  const handleDeleteSavedBlueprint = (name: string) => {
    deleteBlueprintFromWorkspaceLibrary(name)
    setSavedBlueprints(getSavedWorkspaceBlueprints())
    toast.info(`Deleted "${name}" from local library`)
  }

  // ─── Cloud Sync Actions (Phase 43) ──────────────────────────────────────────
  const handleSaveToCloud = async () => {
    setIsSavingToCloud(true)
    try {
      const res = await saveBlueprintToCloud(generatedExport)
      if (res.success) {
        setIsSavedToCloud(true)
        mutateCloud()
        toast.success(`Synced "${generatedExport.metadata.name}" to Cloud Library!`)
        setTimeout(() => setIsSavedToCloud(false), 3000)
      } else {
        toast.error(res.error || "Failed to sync to cloud")
      }
    } finally {
      setIsSavingToCloud(false)
    }
  }

  const handleDeleteCloudBlueprint = async (id: string, name: string) => {
    const ok = await deleteBlueprintFromCloud(id)
    if (ok) {
      mutateCloud()
      toast.info(`Deleted "${name}" from Cloud Library`)
    } else {
      toast.error("Failed to delete cloud blueprint")
    }
  }

  // ─── Vault Actions ─────────────────────────────────────────────────────────
  const handleTakeManualSnapshot = () => {
    const snap = saveCanvasSnapshot(rootNodes, stickyNotes, "Manual Canvas Snapshot")
    setSnapshots(getCanvasSnapshots())
    toast.success(`Snapshot saved to vault (${snap.nodeCount} steps, ${snap.stickyNotesCount} notes)`)
  }

  const handleRestoreFromVault = (snapshot: CanvasSnapshot) => {
    saveCanvasSnapshot(rootNodes, stickyNotes, "Pre-restore Canvas Backup")
    loadTree(snapshot.nodes, snapshot.stickyNotes)
    setSnapshots(getCanvasSnapshots())
    onClose()
    toast.success(`Canvas restored to snapshot from ${snapshot.formattedTime}`, {
      description: `${snapshot.nodeCount} steps loaded onto canvas`,
    })
  }

  const handleDeleteSnapshot = (id: string) => {
    deleteCanvasSnapshot(id)
    setSnapshots(getCanvasSnapshots())
    toast.info("Snapshot removed from vault")
  }

  const handleClearAllSnapshots = () => {
    clearCanvasSnapshots()
    setSnapshots([])
    toast.info("Canvas snapshot vault cleared")
  }

  // Filter gallery items
  const allGalleryItems = useMemo(() => {
    if (galleryFilter === "cloud") return cloudBlueprints
    if (galleryFilter === "saved") return savedBlueprints
    if (galleryFilter === "all") return [...CURATED_BLUEPRINTS, ...cloudBlueprints, ...savedBlueprints]
    return [...CURATED_BLUEPRINTS, ...cloudBlueprints, ...savedBlueprints].filter(bp =>
      bp.metadata.tags?.includes(galleryFilter)
    )
  }, [galleryFilter, savedBlueprints, cloudBlueprints])

  const filteredGalleryItems = useMemo(() => {
    if (!gallerySearch.trim()) return allGalleryItems
    const q = gallerySearch.toLowerCase().trim()
    return allGalleryItems.filter(bp =>
      bp.metadata.name.toLowerCase().includes(q) ||
      (bp.metadata.description && bp.metadata.description.toLowerCase().includes(q)) ||
      (bp.metadata.branding?.agencyName && bp.metadata.branding.agencyName.toLowerCase().includes(q))
    )
  }, [allGalleryItems, gallerySearch])

  // Channels required by imported blueprint
  const requiredChannels = validationResult?.stats?.channels || []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
        className="w-full max-w-5xl bg-card border border-border rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/20">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <ElesiumLogo className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-foreground tracking-tight">
                  Sequence Blueprint Engine
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20">
                  Make / n8n Spec
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Export, import, browse curated templates, and safeguard workflow blueprints
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-border bg-muted/40 px-6 pt-2 gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("gallery")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors border-b-2 cursor-pointer",
              activeTab === "gallery"
                ? "border-primary text-primary bg-card"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Compass size={14} />
            <span>Blueprint Gallery</span>
            <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-muted border border-border">
              {CURATED_BLUEPRINTS.length + cloudBlueprints.length + savedBlueprints.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("export")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors border-b-2 cursor-pointer",
              activeTab === "export"
                ? "border-primary text-primary bg-card"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Download size={14} />
            <span>Export Current Canvas</span>
            <span className="px-1.5 py-0.2 rounded text-[10px] bg-muted border border-border">
              {exportStats.nodeCount} steps
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("import")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors border-b-2 cursor-pointer",
              activeTab === "import"
                ? "border-primary text-primary bg-card"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Upload size={14} />
            <span>Import / Drop File</span>
            {importedBlueprint && (
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            )}
          </button>

          <button
            type="button"
            onClick={() => {
              setSnapshots(getCanvasSnapshots())
              setActiveTab("vault")
            }}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors border-b-2 cursor-pointer ml-auto",
              activeTab === "vault"
                ? "border-primary text-primary bg-card"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <History size={14} />
            <span>Rollback Vault</span>
            {snapshots.length > 0 && (
              <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-primary/10 text-primary border border-primary/20">
                {snapshots.length}
              </span>
            )}
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === "gallery" ? (
            /* ══════════════════════════════════════════════════════════════════════
               GALLERY TAB (Phase 3 Curated Templates & Workspace Library)
               ══════════════════════════════════════════════════════════════════════ */
            <div className="space-y-5">
              {/* Filter and Search Bar */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 border-b border-border pb-4">
                <div className="flex flex-wrap items-center gap-1.5">
                  {[
                    { id: "all", label: "All Templates" },
                    { id: "enterprise", label: "Enterprise" },
                    { id: "social-selling", label: "Social Selling" },
                    { id: "multichannel", label: "Multichannel" },
                    { id: "fast-cadence", label: "Direct Blitz" },
                    { id: "cloud", label: `Cloud Library (${cloudBlueprints.length})` },
                    { id: "saved", label: `Local (${savedBlueprints.length})` },
                  ].map(tab => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setGalleryFilter(tab.id)}
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer",
                        galleryFilter === tab.id
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="relative w-full sm:w-64">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={gallerySearch}
                    onChange={e => setGallerySearch(e.target.value)}
                    placeholder="Search templates or agencies..."
                    className="w-full h-8 pl-8 pr-3 rounded-lg bg-background border border-border text-xs focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Blueprint Cards Grid */}
              {filteredGalleryItems.length === 0 ? (
                <div className="border border-dashed border-border rounded-2xl p-10 flex flex-col items-center justify-center text-center gap-3 bg-muted/10">
                  <div className="w-12 h-12 rounded-2xl bg-muted border border-border flex items-center justify-center text-muted-foreground">
                    <Compass size={24} />
                  </div>
                  <h4 className="text-sm font-semibold text-foreground">
                    No matching templates found
                  </h4>
                  <p className="text-xs text-muted-foreground max-w-md">
                    Try adjusting your search terms or switch category filters.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {filteredGalleryItems.map(bp => {
                    const stats = bp.metadata.stats || calculateBlueprintStats(bp.sequence.rootNodes, bp.sequence.stickyNotes)
                    const accent = bp.metadata.branding?.accentColor || "#6366f1"
                    const isCloudSynced = Boolean(bp.metadata.id)
                    const isUserSaved = savedBlueprints.some(sb => sb.metadata.name === bp.metadata.name)

                    return (
                      <div
                        key={bp.metadata.name}
                        className="rounded-xl border p-4 flex flex-col justify-between gap-3 bg-card/70 hover:border-primary/50 transition-all relative overflow-hidden group shadow-2xs"
                        style={{ borderColor: `${accent}30` }}
                      >
                        <div
                          className="absolute top-0 left-0 right-0 h-1"
                          style={{ backgroundColor: accent }}
                        />

                        {/* Card Header */}
                        <div>
                          <div className="flex items-center justify-between gap-2 pt-1">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span
                                className="px-2 py-0.5 rounded text-[10px] font-bold text-white shadow-2xs truncate"
                                style={{ backgroundColor: accent }}
                              >
                                {bp.metadata.branding?.agencyName || "Curated Blueprint"}
                              </span>
                              {isCloudSynced && (
                                <span className="px-1.5 py-0.2 rounded text-[9px] font-mono bg-primary/10 text-primary border border-primary/20 flex items-center gap-0.5 shrink-0">
                                  <Cloud size={9} />
                                  <span>Cloud</span>
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                              {bp.metadata.version || "v1.0.0"}
                            </span>
                          </div>

                          <h4 className="text-sm font-bold text-foreground mt-2 line-clamp-1">
                            {bp.metadata.name}
                          </h4>
                          {bp.metadata.description && (
                            <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                              {bp.metadata.description}
                            </p>
                          )}
                        </div>

                        {/* Metrics summary */}
                        <div className="grid grid-cols-3 gap-1.5 py-2 border-y border-border/50 text-center">
                          <div className="bg-muted/40 p-1.5 rounded-md">
                            <div className="text-xs font-bold text-foreground">{stats.nodeCount}</div>
                            <div className="text-[9px] text-muted-foreground">Steps</div>
                          </div>
                          <div className="bg-muted/40 p-1.5 rounded-md">
                            <div className="text-xs font-bold text-foreground">{stats.conditionCount}</div>
                            <div className="text-[9px] text-muted-foreground">Branches</div>
                          </div>
                          <div className="bg-muted/40 p-1.5 rounded-md">
                            <div className="text-xs font-bold text-foreground">{stats.delayDaysTotal}d</div>
                            <div className="text-[9px] text-muted-foreground">Cadence</div>
                          </div>
                        </div>

                        {/* Variables pills */}
                        {stats.requiredVariables.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {stats.requiredVariables.slice(0, 3).map(v => (
                              <span
                                key={v}
                                className="px-1.5 py-0.2 rounded text-[9px] font-mono bg-muted text-muted-foreground border border-border"
                              >
                                {`{{${v}}}`}
                              </span>
                            ))}
                            {stats.requiredVariables.length > 3 && (
                              <span className="text-[9px] text-muted-foreground font-mono">
                                +{stats.requiredVariables.length - 3}
                              </span>
                            )}
                          </div>
                        )}

                        {/* Action buttons */}
                        <div className="flex items-center gap-2 pt-2 border-t border-border/40 mt-auto">
                          <button
                            type="button"
                            onClick={() => handleInspectBlueprintFromGallery(bp)}
                            className="flex-1 h-8 px-2.5 rounded-lg bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold flex items-center justify-center gap-1.5 border border-border transition-colors cursor-pointer"
                          >
                            <Sliders size={12} />
                            <span>Inspect</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleDirectLoadFromGallery(bp)}
                            className="h-8 px-3 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer shadow-2xs"
                          >
                            <ArrowRight size={13} />
                            <span>Load</span>
                          </button>

                          {isCloudSynced ? (
                            <button
                              type="button"
                              onClick={() => handleDeleteCloudBlueprint(bp.metadata.id!, bp.metadata.name)}
                              className="p-1.5 text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                              title="Delete from cloud library"
                            >
                              <Trash2 size={13} />
                            </button>
                          ) : isUserSaved ? (
                            <button
                              type="button"
                              onClick={() => handleDeleteSavedBlueprint(bp.metadata.name)}
                              className="p-1.5 text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                              title="Remove from local library"
                            >
                              <Trash2 size={13} />
                            </button>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          ) : activeTab === "export" ? (
            /* ══════════════════════════════════════════════════════════════════════
               EXPORT TAB
               ══════════════════════════════════════════════════════════════════════ */
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Left Column: Metadata & Agency Branding Form */}
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground flex items-center gap-1.5">
                    <span>Blueprint Name</span>
                    <span className="text-destructive">*</span>
                  </label>
                  <input
                    type="text"
                    value={blueprintName}
                    onChange={e => setBlueprintName(e.target.value)}
                    placeholder="e.g. Enterprise Tier-1 Account Executive Sequence"
                    className="w-full h-9 px-3 rounded-lg bg-background border border-border text-xs focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">
                    Description & Strategy Notes
                  </label>
                  <textarea
                    value={blueprintDescription}
                    onChange={e => setBlueprintDescription(e.target.value)}
                    placeholder="Describe target ICP, timing cadence, and expected conversion targets..."
                    rows={3}
                    className="w-full p-3 rounded-lg bg-background border border-border text-xs focus:outline-hidden focus:ring-1 focus:ring-primary resize-none"
                  />
                </div>

                {/* Agency & Author Branding */}
                <div className="p-3.5 rounded-xl border border-border/80 bg-muted/20 space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                    <Palette size={14} className="text-primary" />
                    <span>Agency / Brand Identity</span>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground font-medium">Agency / Company</label>
                      <input
                        type="text"
                        value={agencyName}
                        onChange={e => setAgencyName(e.target.value)}
                        className="w-full h-8 px-2.5 rounded-md bg-background border border-border text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground font-medium">Author / Architect</label>
                      <input
                        type="text"
                        value={authorName}
                        onChange={e => setAuthorName(e.target.value)}
                        className="w-full h-8 px-2.5 rounded-md bg-background border border-border text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground font-medium">Brand Accent Color</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={accentColor}
                          onChange={e => setAccentColor(e.target.value)}
                          className="w-7 h-7 rounded border border-border cursor-pointer bg-transparent"
                        />
                        <span className="font-mono text-xs text-muted-foreground">{accentColor}</span>
                      </div>
                    </div>
                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground font-medium">Agency Website (optional)</label>
                      <input
                        type="url"
                        value={agencyWebsite}
                        onChange={e => setAgencyWebsite(e.target.value)}
                        placeholder="https://agency.com"
                        className="w-full h-8 px-2.5 rounded-md bg-background border border-border text-xs"
                      />
                    </div>
                  </div>
                </div>

                {/* Sanitization Options */}
                <div className="space-y-2 pt-1">
                  <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
                    <input
                      type="checkbox"
                      checked={sanitizeIds}
                      onChange={e => setSanitizeIds(e.target.checked)}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <span className="font-medium">Sanitize workspace and account IDs (Recommended)</span>
                  </label>
                  <p className="text-[11px] text-muted-foreground pl-5">
                    Strips sensitive tenant UUIDs, inline secrets, and private credentials so the blueprint is portable and safe to share.
                  </p>

                  <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer pt-1">
                    <input
                      type="checkbox"
                      checked={includeSticky}
                      onChange={e => setIncludeSticky(e.target.checked)}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <span className="font-medium">Include canvas sticky notes ({stickyNotes.length})</span>
                  </label>
                </div>
              </div>

              {/* Right Column: Branded Blueprint Preview Card */}
              <div className="flex flex-col gap-4">
                <div className="text-xs font-semibold text-muted-foreground">
                  Branded Blueprint Preview Card
                </div>

                <div
                  className="rounded-xl border p-5 flex flex-col gap-4 relative overflow-hidden bg-card/60 backdrop-blur-xs"
                  style={{ borderColor: `${accentColor}40` }}
                >
                  <div
                    className="absolute top-0 left-0 right-0 h-1.5"
                    style={{ backgroundColor: accentColor }}
                  />

                  {/* Header */}
                  <div className="flex items-start justify-between gap-3 pt-1">
                    <div>
                      <div className="flex items-center gap-2">
                        <span
                          className="px-2 py-0.5 rounded text-[10px] font-bold text-white shadow-2xs"
                          style={{ backgroundColor: accentColor }}
                        >
                          {agencyName}
                        </span>
                        <span className="text-[10px] text-muted-foreground">v1.0.0</span>
                      </div>
                      <h3 className="text-sm font-bold text-foreground mt-1 line-clamp-1">
                        {blueprintName || "Untitled Outbound Blueprint"}
                      </h3>
                      {blueprintDescription && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {blueprintDescription}
                        </p>
                      )}
                    </div>

                    <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0">
                      <ElesiumLogo className="w-4 h-4 text-primary" />
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div className="grid grid-cols-3 gap-2 py-2 border-y border-border/60">
                    <div className="bg-muted/40 p-2 rounded-lg text-center">
                      <div className="text-base font-bold text-foreground">{exportStats.nodeCount}</div>
                      <div className="text-[10px] text-muted-foreground font-medium">Total Steps</div>
                    </div>
                    <div className="bg-muted/40 p-2 rounded-lg text-center">
                      <div className="text-base font-bold text-foreground">{exportStats.conditionCount}</div>
                      <div className="text-[10px] text-muted-foreground font-medium">Conditions</div>
                    </div>
                    <div className="bg-muted/40 p-2 rounded-lg text-center">
                      <div className="text-base font-bold text-foreground">{exportStats.delayDaysTotal}d</div>
                      <div className="text-[10px] text-muted-foreground font-medium">Cadence Span</div>
                    </div>
                  </div>

                  {/* Required Variables */}
                  {exportStats.requiredVariables.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="text-[10px] uppercase font-bold text-muted-foreground/80 tracking-wider">
                        Required Variables
                      </span>
                      <div className="flex flex-wrap gap-1">
                        {exportStats.requiredVariables.map(v => (
                          <span
                            key={v}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground border border-border"
                          >
                            {`{{${v}}}`}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Footer Badge */}
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground/70 pt-2 border-t border-border/40">
                    <span>Designed by {authorName}</span>
                    <span className="font-mono">elein-blueprint-v1</span>
                  </div>
                </div>

                {/* Export Action Buttons */}
                <div className="flex flex-col gap-2 pt-2 mt-auto">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        downloadBlueprintFile(generatedExport, `${blueprintName || "elein_workflow"}.elein`)
                        toast.success("Downloaded .elein blueprint file")
                      }}
                      className="flex-1 h-10 px-4 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold flex items-center justify-center gap-2 transition-colors cursor-pointer shadow-sm"
                    >
                      <Download size={15} />
                      <span>Download .elein</span>
                    </button>

                    <button
                      type="button"
                      onClick={async () => {
                        const ok = await copyBlueprintToClipboard(generatedExport)
                        if (ok) {
                          setIsCopied(true)
                          toast.success("Blueprint JSON copied to clipboard")
                          setTimeout(() => setIsCopied(false), 2500)
                        } else {
                          toast.error("Failed to copy to clipboard")
                        }
                      }}
                      className="h-10 px-4 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold flex items-center justify-center gap-2 border border-border transition-colors cursor-pointer"
                    >
                      {isCopied ? <Check size={15} className="text-emerald-500" /> : <Copy size={15} />}
                      <span>{isCopied ? "Copied" : "Copy JSON"}</span>
                    </button>
                  </div>

                  {/* Cloud Sync and Local Library Save Buttons */}
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      onClick={handleSaveToCloud}
                      disabled={isSavingToCloud}
                      className="flex-1 h-9 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold flex items-center justify-center gap-2 border border-primary/20 transition-colors cursor-pointer disabled:opacity-50"
                    >
                      <CloudUpload size={14} className={isSavingToCloud ? "animate-bounce" : ""} />
                      <span>{isSavingToCloud ? "Syncing to Cloud..." : isSavedToCloud ? "Synced to Cloud!" : "Save to Cloud Library (Team Sync)"}</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleSaveToWorkspaceLibrary}
                      className="h-9 px-3.5 rounded-xl bg-muted/60 hover:bg-muted text-foreground text-xs font-semibold flex items-center justify-center gap-1.5 border border-border/80 transition-colors cursor-pointer"
                      title="Save to local browser storage"
                    >
                      {isSavedToLibrary ? <Check size={14} className="text-emerald-500" /> : <BookmarkPlus size={14} className="text-muted-foreground" />}
                      <span>{isSavedToLibrary ? "Saved Local" : "Save Local"}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === "import" ? (
            /* ══════════════════════════════════════════════════════════════════════
               IMPORT TAB
               ══════════════════════════════════════════════════════════════════════ */
            <div className="space-y-6">
              {/* Import Method Toggle */}
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setImportTab("file")}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer",
                      importTab === "file"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:text-foreground"
                    )}
                  >
                    Upload / Drop File (.elein)
                  </button>
                  <button
                    type="button"
                    onClick={() => setImportTab("paste")}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer",
                      importTab === "paste"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:text-foreground"
                    )}
                  >
                    Paste JSON Text
                  </button>
                </div>

                {importedBlueprint && (
                  <button
                    type="button"
                    onClick={() => {
                      setImportedBlueprint(null)
                      setValidationResult(null)
                      setPastedJson("")
                    }}
                    className="text-xs text-muted-foreground hover:text-destructive transition-colors flex items-center gap-1 cursor-pointer"
                  >
                    <RefreshCw size={12} />
                    <span>Clear Blueprint</span>
                  </button>
                )}
              </div>

              {importTab === "file" ? (
                /* Drag & Drop Zone */
                <div
                  onDragOver={e => {
                    e.preventDefault()
                    setIsDragOver(true)
                  }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={e => {
                    e.preventDefault()
                    setIsDragOver(false)
                    const file = e.dataTransfer.files?.[0]
                    if (file) handleFileSelected(file)
                  }}
                  onClick={() => fileInputRef.current?.click()}
                  className={cn(
                    "border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center gap-3 text-center transition-all cursor-pointer",
                    isDragOver
                      ? "border-primary bg-primary/10 scale-[1.01]"
                      : "border-border hover:border-primary/50 bg-muted/10 hover:bg-muted/20"
                  )}
                >
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept=".elein,.json,application/json"
                    className="hidden"
                    onChange={e => {
                      const file = e.target.files?.[0]
                      if (file) handleFileSelected(file)
                    }}
                  />

                  <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                    <Upload size={24} />
                  </div>

                  <div>
                    <h3 className="text-sm font-semibold text-foreground">
                      Drag & Drop .elein or .json Blueprint File Here
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Compatible with Make.com / n8n workflow export standards
                    </p>
                  </div>

                  <span className="px-3 py-1 rounded-full text-xs font-medium bg-muted border border-border text-foreground hover:bg-muted/80">
                    Browse files
                  </span>
                </div>
              ) : (
                /* JSON Paste Area */
                <div className="space-y-3">
                  <textarea
                    value={pastedJson}
                    onChange={e => setPastedJson(e.target.value)}
                    placeholder="Paste exported .elein or JSON blueprint text here..."
                    rows={7}
                    className="w-full p-4 rounded-xl bg-background border border-border font-mono text-xs focus:outline-hidden focus:ring-1 focus:ring-primary resize-none"
                  />
                  <button
                    type="button"
                    onClick={handleJsonPasteValidate}
                    className="px-4 py-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold flex items-center gap-2 cursor-pointer transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    <span>Validate & Load JSON</span>
                  </button>
                </div>
              )}

              {/* Inspection Card when Blueprint is Loaded */}
              {importedBlueprint && validationResult && (
                <div className="space-y-4 pt-2 animate-in fade-in slide-in-from-bottom-2 duration-200">
                  <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span
                            className="px-2 py-0.5 rounded text-[10px] font-bold text-white shadow-2xs"
                            style={{
                              backgroundColor:
                                importedBlueprint.metadata?.branding?.accentColor || "#6366f1",
                            }}
                          >
                            {importedBlueprint.metadata?.branding?.agencyName || "External Blueprint"}
                          </span>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {importedBlueprint.metadata?.version || "v1.0.0"}
                          </span>
                        </div>
                        <h4 className="text-sm font-bold text-foreground mt-1">
                          {importedBlueprint.metadata?.name}
                        </h4>
                        {importedBlueprint.metadata?.description && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {importedBlueprint.metadata.description}
                          </p>
                        )}
                      </div>

                      <div className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5 shrink-0">
                        <CheckCircle2 size={12} />
                        <span>Ready to Import</span>
                      </div>
                    </div>

                    {/* Stats summary */}
                    <div className="grid grid-cols-4 gap-2 pt-2 border-t border-border/50 text-center">
                      <div className="bg-background/60 p-2 rounded-lg">
                        <div className="text-sm font-bold text-foreground">
                          {validationResult.stats.nodeCount}
                        </div>
                        <div className="text-[10px] text-muted-foreground font-medium">Steps</div>
                      </div>
                      <div className="bg-background/60 p-2 rounded-lg">
                        <div className="text-sm font-bold text-foreground">
                          {validationResult.stats.conditionCount}
                        </div>
                        <div className="text-[10px] text-muted-foreground font-medium">Branches</div>
                      </div>
                      <div className="bg-background/60 p-2 rounded-lg">
                        <div className="text-sm font-bold text-foreground">
                          {validationResult.stats.delayDaysTotal}d
                        </div>
                        <div className="text-[10px] text-muted-foreground font-medium">Cadence</div>
                      </div>
                      <div className="bg-background/60 p-2 rounded-lg">
                        <div className="text-sm font-bold text-foreground">
                          {validationResult.stats.stickyNotesCount}
                        </div>
                        <div className="text-[10px] text-muted-foreground font-medium">Notes</div>
                      </div>
                    </div>

                    {/* Channel Pre-Flight Compatibility Warning (Phase 2 Hardening) */}
                    {requiredChannels.length > 0 && (
                      <div className="pt-2 border-t border-border/50 space-y-2">
                        <div className="flex items-center justify-between text-xs font-semibold text-foreground">
                          <span className="flex items-center gap-1.5">
                            <Shield size={13} className="text-primary" />
                            <span>Channel Pre-Flight Compatibility</span>
                          </span>
                          <span className="text-[10px] font-mono text-muted-foreground">
                            {activeAccounts.length} active senders connected
                          </span>
                        </div>

                        {requiredChannels.includes("linkedin") && !hasActiveLinkedIn && (
                          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-start gap-2.5 text-xs text-amber-200">
                            <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
                            <div className="space-y-1">
                              <span className="font-semibold text-amber-300">
                                LinkedIn Account Required
                              </span>
                              <p className="text-[11px] text-muted-foreground leading-relaxed">
                                This blueprint contains LinkedIn outreach steps (e.g. Connection Request, InMail, Profile Visits), but no active LinkedIn accounts are connected in this workspace. Outreach will hold execution until a sender is attached.
                              </p>
                            </div>
                          </div>
                        )}

                        {requiredChannels.includes("email") && !hasActiveEmail && (
                          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-start gap-2.5 text-xs text-amber-200">
                            <Mail size={15} className="text-amber-400 shrink-0 mt-0.5" />
                            <div className="space-y-1">
                              <span className="font-semibold text-amber-300">
                                Email Sender Pod Required
                              </span>
                              <p className="text-[11px] text-muted-foreground leading-relaxed">
                                This blueprint contains Email outreach steps, but no active Email sender accounts or SMTP pods are connected.
                              </p>
                            </div>
                          </div>
                        )}

                        {((!requiredChannels.includes("linkedin") || hasActiveLinkedIn) &&
                          (!requiredChannels.includes("email") || hasActiveEmail)) && (
                          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-2 text-xs text-emerald-400">
                            <ShieldCheck size={14} className="text-emerald-400 shrink-0" />
                            <span>
                              Pre-flight verified: Active sender accounts are configured for required channels ({requiredChannels.join(", ")}).
                            </span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Variable Reconciliation & Fallback Mapper (Phase 2 Hardening) */}
                    {variableAudit.length > 0 && (
                      <div className="pt-2 border-t border-border/50 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                            <Sliders size={13} className="text-primary" />
                            <span>Template Variable Reconciliation & Fallbacks</span>
                          </span>
                          <button
                            type="button"
                            onClick={handleApplyFallbacks}
                            className="px-2.5 py-1 rounded-md text-[10px] font-semibold bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors cursor-pointer"
                          >
                            Apply Fallbacks to Sequence
                          </button>
                        </div>

                        <div className="bg-background/50 border border-border/60 rounded-xl p-2.5 space-y-2 max-h-48 overflow-y-auto">
                          {variableAudit.map(v => (
                            <div
                              key={v.name}
                              className="flex items-center justify-between gap-3 text-xs p-1.5 rounded-lg bg-muted/30 border border-border/40"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="font-mono text-[11px] text-foreground font-semibold px-1.5 py-0.5 bg-muted rounded border border-border shrink-0">
                                  {`{{${v.name}}}`}
                                </span>
                                <span className="text-[10px] text-muted-foreground shrink-0">
                                  {v.occurrences}x
                                </span>
                                {!v.hasFallback && (
                                  <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20 shrink-0">
                                    No Fallback
                                  </span>
                                )}
                              </div>

                              <div className="flex items-center gap-1.5">
                                <span className="text-[10px] text-muted-foreground shrink-0">Fallback:</span>
                                <input
                                  type="text"
                                  value={fallbackOverrides[v.name] ?? ""}
                                  onChange={e =>
                                    setFallbackOverrides(prev => ({
                                      ...prev,
                                      [v.name]: e.target.value,
                                    }))
                                  }
                                  placeholder={v.suggestedFallback}
                                  className="h-6 w-32 px-2 rounded bg-background border border-border text-[11px] font-mono focus:outline-hidden focus:ring-1 focus:ring-primary"
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                        <p className="text-[10px] text-muted-foreground">
                          Fallbacks protect against blank messages when prospect records have empty fields (e.g. missing company or title).
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Mode Selector */}
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-foreground">
                      Import Destination Mode
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <label
                        className={cn(
                          "p-3 rounded-xl border flex flex-col gap-1 cursor-pointer transition-colors",
                          importMode === "replace"
                            ? "border-primary bg-primary/10"
                            : "border-border hover:bg-muted/40"
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="importMode"
                            checked={importMode === "replace"}
                            onChange={() => setImportMode("replace")}
                            className="text-primary focus:ring-primary"
                          />
                          <span className="text-xs font-bold text-foreground">Replace Canvas</span>
                        </div>
                        <span className="text-[11px] text-muted-foreground pl-5">
                          Clears current steps and loads the blueprint from root node. A snapshot is automatically saved to the vault.
                        </span>
                      </label>

                      <label
                        className={cn(
                          "p-3 rounded-xl border flex flex-col gap-1 cursor-pointer transition-colors",
                          importMode === "append"
                            ? "border-primary bg-primary/10"
                            : "border-border hover:bg-muted/40"
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="importMode"
                            checked={importMode === "append"}
                            onChange={() => setImportMode("append")}
                            className="text-primary focus:ring-primary"
                          />
                          <span className="text-xs font-bold text-foreground">Append & Merge</span>
                        </div>
                        <span className="text-[11px] text-muted-foreground pl-5">
                          Preserves existing steps and adds blueprint steps alongside with automatic spatial offset and regenerated IDs.
                        </span>
                      </label>
                    </div>
                  </div>

                  {/* Import Button */}
                  <div className="flex items-center justify-end gap-3 pt-2">
                    <button
                      type="button"
                      onClick={onClose}
                      className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => handleConfirmImport()}
                      className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold flex items-center gap-2 shadow-sm transition-colors cursor-pointer"
                    >
                      <ArrowRight size={14} />
                      <span>Confirm & Import Sequence</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* ══════════════════════════════════════════════════════════════════════
               ROLLBACK VAULT TAB (Phase 1 Hardening)
               ══════════════════════════════════════════════════════════════════════ */
            <div className="space-y-5">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Canvas Rollback Vault
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Safety snapshots automatically captured before every blueprint import or on demand
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleTakeManualSnapshot}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <Camera size={13} />
                    <span>Snapshot Canvas Now</span>
                  </button>

                  {snapshots.length > 0 && (
                    <button
                      type="button"
                      onClick={handleClearAllSnapshots}
                      className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
                    >
                      Clear Vault
                    </button>
                  )}
                </div>
              </div>

              {snapshots.length === 0 ? (
                <div className="border border-dashed border-border rounded-2xl p-10 flex flex-col items-center justify-center text-center gap-3 bg-muted/10">
                  <div className="w-12 h-12 rounded-2xl bg-muted border border-border flex items-center justify-center text-muted-foreground">
                    <History size={24} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-foreground">
                      No Snapshots in Vault
                    </h4>
                    <p className="text-xs text-muted-foreground max-w-md mt-1">
                      Snapshots are automatically created before you import or replace blueprints, so you can always roll back. You can also take a snapshot anytime before experimenting with complex sequences.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleTakeManualSnapshot}
                    className="mt-2 px-4 py-2 rounded-xl text-xs font-semibold bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors cursor-pointer flex items-center gap-2"
                  >
                    <Camera size={14} />
                    <span>Take First Snapshot ({exportStats.nodeCount} steps)</span>
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {snapshots.map(snap => (
                    <div
                      key={snap.id}
                      className="p-4 rounded-xl border border-border bg-card hover:border-primary/40 transition-colors flex items-center justify-between gap-4"
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-foreground truncate">
                            {snap.label}
                          </span>
                          <span className="text-[10px] font-mono text-muted-foreground px-2 py-0.5 rounded bg-muted border border-border">
                            {snap.formattedTime}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                          <span>{snap.nodeCount} sequence steps</span>
                          <span>•</span>
                          <span>{snap.stickyNotesCount} sticky notes</span>
                          <span>•</span>
                          <span>{new Date(snap.timestamp).toLocaleDateString()}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleRestoreFromVault(snap)}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground flex items-center gap-1.5 transition-colors cursor-pointer shadow-2xs"
                        >
                          <Undo2 size={13} />
                          <span>Restore to Canvas</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleDeleteSnapshot(snap.id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
                          aria-label="Delete snapshot"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}
