import { v4 as uuidv4 } from "uuid"
import { HR_NODE_DEFS, type EINodeType } from "./eiNodeDefs"
import type { SeqTreeNode, StickyNote } from "@campaigns/eiTreeStore"

export interface EleInBlueprintAuthor {
  agencyName?: string
  authorName?: string
  accentColor?: string
  badge?: string
  website?: string
}

export interface EleInBlueprintStats {
  nodeCount: number
  actionCount: number
  conditionCount: number
  aiCount: number
  delayDaysTotal: number
  stickyNotesCount: number
  requiredVariables: string[]
  channels: Array<"linkedin" | "email" | "voice" | "multichannel">
}

export interface EleInBlueprintMetadata {
  id?: string
  name: string
  description?: string
  version: string
  schemaVersion: "elein-blueprint-v1"
  exportedAt: string
  branding?: EleInBlueprintAuthor
  tags?: string[]
  stats?: EleInBlueprintStats
}

export interface EleInBlueprint {
  schema: "elein-blueprint-v1"
  metadata: EleInBlueprintMetadata
  sequence: {
    rootNodes: SeqTreeNode[]
    stickyNotes?: StickyNote[]
  }
  options?: {
    autoWithdrawDays?: number
    timezone?: string
    dailyLimit?: number
  }
}

export interface BlueprintValidationResult {
  isValid: boolean
  errors: string[]
  warnings: string[]
  stats: EleInBlueprintStats
  parsedBlueprint: EleInBlueprint | null
}

export type ImportMode = "replace" | "append"

// ─── Variable Audit & Reconciliation ─────────────────────────────────────────
export interface VariableAuditItem {
  name: string
  rawTokens: string[]
  hasFallback: boolean
  currentFallback?: string
  suggestedFallback: string
  occurrences: number
}

export const COMMON_SMART_FALLBACKS: Record<string, string> = {
  first_name: "there",
  last_name: "",
  company: "your company",
  company_name: "your team",
  job_title: "your role",
  title: "your role",
  industry: "your space",
  city: "your area",
  location: "your region",
  funding_round: "recent growth",
  tech_stack: "modern tools",
  icebreaker: "",
  recent_post_topic: "recent insights",
}

// ─── Variable Extraction Helper ──────────────────────────────────────────────
export function extractTemplateVariables(text: string): string[] {
  if (!text || typeof text !== "string") return []
  const matches = text.match(/\{\{([a-zA-Z0-9_]+)(?:\|[^}]*)?\}\}/g)
  if (!matches) return []
  const vars = new Set<string>()
  for (const m of matches) {
    const raw = m.slice(2, -2).trim()
    const varName = raw.split("|")[0].trim()
    if (varName) vars.add(varName)
  }
  return Array.from(vars)
}

// ─── Comprehensive Variable Audit ────────────────────────────────────────────
export function auditBlueprintVariables(rootNodes: SeqTreeNode[]): VariableAuditItem[] {
  const auditMap = new Map<string, { rawTokens: Set<string>; hasFallback: boolean; fallbackVal?: string; count: number }>()

  function scanText(text: string) {
    if (!text || typeof text !== "string") return
    const matches = text.match(/\{\{([a-zA-Z0-9_]+)(\|[^}]*)?\}\}/g)
    if (!matches) return

    for (const m of matches) {
      const inner = m.slice(2, -2).trim()
      const parts = inner.split("|")
      const varName = parts[0].trim()
      const fallbackVal = parts.length > 1 ? parts.slice(1).join("|").trim() : undefined
      const hasFb = fallbackVal !== undefined && fallbackVal.length > 0

      const existing = auditMap.get(varName) || {
        rawTokens: new Set<string>(),
        hasFallback: true,
        fallbackVal: undefined,
        count: 0,
      }

      existing.rawTokens.add(m)
      existing.count++
      if (!hasFb) {
        existing.hasFallback = false
      } else if (!existing.fallbackVal) {
        existing.fallbackVal = fallbackVal
      }
      auditMap.set(varName, existing)
    }
  }

  function walk(node: SeqTreeNode) {
    if (node.data) {
      for (const val of Object.values(node.data)) {
        if (typeof val === "string") {
          scanText(val)
        }
      }
    }
    if (node.children) {
      for (const branch of Object.values(node.children)) {
        if (Array.isArray(branch)) {
          for (const child of branch) walk(child)
        }
      }
    }
  }

  for (const root of rootNodes) walk(root)

  return Array.from(auditMap.entries()).map(([name, item]) => ({
    name,
    rawTokens: Array.from(item.rawTokens),
    hasFallback: item.hasFallback,
    currentFallback: item.fallbackVal,
    suggestedFallback: COMMON_SMART_FALLBACKS[name.toLowerCase()] ?? "there",
    occurrences: item.count,
  }))
}

// ─── Apply Variable Fallbacks to Tree ────────────────────────────────────────
export function applyVariableFallbacksToTree(
  rootNodes: SeqTreeNode[],
  fallbackOverrides: Record<string, string>
): SeqTreeNode[] {
  function rewriteText(text: string): string {
    if (!text || typeof text !== "string") return text
    return text.replace(/\{\{([a-zA-Z0-9_]+)(\|[^}]*)?\}\}/g, (match, varName, existingFallback) => {
      const cleanVar = varName.trim()
      const newFallback = fallbackOverrides[cleanVar]
      if (newFallback !== undefined && newFallback.trim().length > 0) {
        return `{{${cleanVar}|${newFallback.trim()}}}`
      }
      if (!existingFallback && COMMON_SMART_FALLBACKS[cleanVar.toLowerCase()]) {
        return `{{${cleanVar}|${COMMON_SMART_FALLBACKS[cleanVar.toLowerCase()]}}}`
      }
      return match
    })
  }

  function transformNode(node: SeqTreeNode): SeqTreeNode {
    const newData: Record<string, any> = { ...node.data }
    for (const [k, v] of Object.entries(newData)) {
      if (typeof v === "string") {
        newData[k] = rewriteText(v)
      }
    }

    const newChildren: Record<string, SeqTreeNode[]> = {}
    if (node.children) {
      for (const [k, branch] of Object.entries(node.children)) {
        newChildren[k] = Array.isArray(branch)
          ? branch.map(child => transformNode(child))
          : []
      }
    }

    return {
      ...node,
      data: newData,
      children: newChildren,
    }
  }

  return rootNodes.map(r => transformNode(r))
}

// ─── Deep Recursive Sanitizer (Layer 1 Security) ─────────────────────────────
const SENSITIVE_KEY_REGEX = /(token|key|secret|password|auth|bearer|cookie|credential|webhook_header|private_ip|session_id|jwt)/i
const STRICT_TENANT_UUID_REGEX = /(workspace_id|account_id|sender_id|lead_id|lead_list_id|execution_state_id|enrollment_id|persona_id|asset_id|user_id)$/i
const PRIVATE_IP_OR_METADATA_REGEX = /https?:\/\/(localhost|127\.0\.0\.1|169\.254\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)/i
const SECRET_TOKEN_STRING_REGEX = /(sk_live_[a-zA-Z0-9]+|sk_test_[a-zA-Z0-9]+|ghp_[a-zA-Z0-9]+|AKIA[0-9A-Z]{16}|xoxb-[a-zA-Z0-9-]+|Bearer\s+[a-zA-Z0-9_\-\.]+)/gi

export function deepSanitizeValue(value: unknown): unknown {
  if (value === null || value === undefined) return value

  if (typeof value === "string") {
    let clean = value
    // Scrub inline tokens
    clean = clean.replace(SECRET_TOKEN_STRING_REGEX, "[REDACTED_SECRET]")
    // Scrub query parameter secrets (?key=... or &token=...)
    clean = clean.replace(/([?&](api_?key|token|auth|secret|password)=)[^&#\s]+/gi, "$1[REDACTED]")
    // Prevent SSRF loopback endpoints in webhook/media URLs
    if (PRIVATE_IP_OR_METADATA_REGEX.test(clean)) {
      clean = clean.replace(PRIVATE_IP_OR_METADATA_REGEX, "https://api.external-service.com/")
    }
    // Neutralize dangerous JavaScript/HTML injection
    clean = clean.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    clean = clean.replace(/javascript\s*:/gi, "blocked-script:")
    return clean
  }

  if (Array.isArray(value)) {
    return value.map(item => deepSanitizeValue(item))
  }

  if (typeof value === "object") {
    const obj = value as Record<string, any>
    const cleanObj: Record<string, any> = {}

    for (const [k, v] of Object.entries(obj)) {
      if (STRICT_TENANT_UUID_REGEX.test(k)) {
        continue
      }
      if (SENSITIVE_KEY_REGEX.test(k)) {
        continue
      }
      cleanObj[k] = deepSanitizeValue(v)
    }
    return cleanObj
  }

  return value
}

// ─── Traverse and Calculate Stats ────────────────────────────────────────────
export function calculateBlueprintStats(
  rootNodes: SeqTreeNode[],
  stickyNotes: StickyNote[] = []
): EleInBlueprintStats {
  let nodeCount = 0
  let actionCount = 0
  let conditionCount = 0
  let aiCount = 0
  let delayDaysTotal = 0
  const variablesSet = new Set<string>()
  const channelsSet = new Set<"linkedin" | "email" | "voice" | "multichannel">()

  function walk(node: SeqTreeNode, visited = new Set<string>()) {
    if (visited.has(node.id)) return
    visited.add(node.id)
    nodeCount++

    const def = (HR_NODE_DEFS as Record<string, any>)[node.type]
    const category = def?.category || ""

    if (category === "conditions") {
      conditionCount++
    } else if (category === "ai") {
      aiCount++
      actionCount++
    } else if (node.type !== "sequence_end") {
      actionCount++
    }

    // Delay accumulation
    const delay = Number(node.data?.delayDays ?? node.data?.delay ?? 0)
    if (!Number.isNaN(delay) && delay > 0) {
      delayDaysTotal += delay
    }

    // Channels detection
    const typeStr = node.type.toLowerCase()
    if (typeStr.includes("email") || typeStr.includes("inmail")) {
      channelsSet.add("email")
    }
    if (typeStr.includes("voice")) {
      channelsSet.add("voice")
    }
    if (typeStr.includes("connection") || typeStr.includes("profile") || typeStr.includes("message")) {
      channelsSet.add("linkedin")
    }

    // Variables inspection
    if (node.data) {
      for (const val of Object.values(node.data)) {
        if (typeof val === "string") {
          for (const v of extractTemplateVariables(val)) {
            variablesSet.add(v)
          }
        }
      }
    }

    if (node.children) {
      for (const branch of Object.values(node.children)) {
        if (Array.isArray(branch)) {
          for (const child of branch) {
            walk(child, visited)
          }
        }
      }
    }
  }

  for (const root of rootNodes) {
    walk(root)
  }

  const channels = Array.from(channelsSet)
  if (channels.length > 1) {
    channels.push("multichannel")
  }

  return {
    nodeCount,
    actionCount,
    conditionCount,
    aiCount,
    delayDaysTotal,
    stickyNotesCount: stickyNotes.length,
    requiredVariables: Array.from(variablesSet),
    channels,
  }
}

// ─── Export Function with Deep Sanitization ──────────────────────────────────
export function exportBlueprint(
  rootNodes: SeqTreeNode[],
  stickyNotes: StickyNote[],
  metadata: Partial<EleInBlueprintMetadata> & { name: string },
  options: { sanitize?: boolean; includeStickyNotes?: boolean } = {}
): EleInBlueprint {
  const sanitize = options.sanitize ?? true
  const includeSticky = options.includeStickyNotes ?? true

  function sanitizeNode(node: SeqTreeNode): SeqTreeNode {
    const rawData = sanitize ? deepSanitizeValue(node.data) : { ...node.data }
    const cleanData: Record<string, any> = (typeof rawData === "object" && rawData !== null) ? rawData : {}

    const cleanChildren: Record<string, SeqTreeNode[]> = {}
    if (node.children) {
      for (const [key, branch] of Object.entries(node.children)) {
        cleanChildren[key] = Array.isArray(branch)
          ? branch.map(child => sanitizeNode(child))
          : []
      }
    }

    return {
      id: node.id,
      type: node.type,
      data: cleanData,
      children: cleanChildren,
      branchEnded: node.branchEnded,
    }
  }

  const cleanRoots = rootNodes.map(r => sanitizeNode(r))
  const cleanNotes: StickyNote[] = includeSticky
    ? stickyNotes.map(sn => ({
        id: sn.id,
        x: sn.x,
        y: sn.y,
        text: String(deepSanitizeValue(sn.text || "")),
        title: sn.title ? String(deepSanitizeValue(sn.title)) : undefined,
        color: sn.color,
        category: sn.category,
        isPinned: sn.isPinned,
        isCollapsed: sn.isCollapsed,
        updatedAt: sn.updatedAt,
      }))
    : []

  const stats = calculateBlueprintStats(cleanRoots, cleanNotes)

  const finalMetadata: EleInBlueprintMetadata = {
    name: metadata.name.trim() || "Exported Workflow Blueprint",
    description: metadata.description?.trim() ? String(deepSanitizeValue(metadata.description.trim())) : "",
    version: metadata.version || "1.0.0",
    schemaVersion: "elein-blueprint-v1",
    exportedAt: new Date().toISOString(),
    branding: {
      agencyName: metadata.branding?.agencyName ? String(deepSanitizeValue(metadata.branding.agencyName)) : "Ele-in Studio",
      authorName: metadata.branding?.authorName ? String(deepSanitizeValue(metadata.branding.authorName)) : "Sequence Architect",
      accentColor: metadata.branding?.accentColor || "#6366f1",
      badge: metadata.branding?.badge ? String(deepSanitizeValue(metadata.branding.badge)) : "Verified Blueprint",
      website: metadata.branding?.website ? String(deepSanitizeValue(metadata.branding.website)) : undefined,
    },
    tags: metadata.tags || ["custom-sequence", "outbound"],
    stats,
  }

  return {
    schema: "elein-blueprint-v1",
    metadata: finalMetadata,
    sequence: {
      rootNodes: cleanRoots,
      stickyNotes: cleanNotes,
    },
  }
}

// ─── Validate Function ───────────────────────────────────────────────────────
export function validateBlueprint(data: unknown): BlueprintValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (!data || typeof data !== "object") {
    return {
      isValid: false,
      errors: ["Invalid Blueprint: payload must be a JSON object."],
      warnings: [],
      stats: {
        nodeCount: 0,
        actionCount: 0,
        conditionCount: 0,
        aiCount: 0,
        delayDaysTotal: 0,
        stickyNotesCount: 0,
        requiredVariables: [],
        channels: [],
      },
      parsedBlueprint: null,
    }
  }

  const obj = data as Record<string, any>

  if (obj.schema !== "elein-blueprint-v1") {
    errors.push("Unsupported schema version: expected 'elein-blueprint-v1'.")
  }

  if (!obj.metadata || typeof obj.metadata !== "object" || !obj.metadata.name) {
    errors.push("Missing or invalid metadata: blueprint must have a name.")
  }

  if (!obj.sequence || !Array.isArray(obj.sequence.rootNodes)) {
    errors.push("Malformed sequence: 'sequence.rootNodes' array is missing.")
  }

  const rootNodes: SeqTreeNode[] = Array.isArray(obj.sequence?.rootNodes)
    ? obj.sequence.rootNodes
    : []
  const stickyNotes: StickyNote[] = Array.isArray(obj.sequence?.stickyNotes)
    ? obj.sequence.stickyNotes
    : []

  if (rootNodes.length === 0) {
    warnings.push("Blueprint contains an empty sequence (0 root nodes).")
  }

  let totalNodesCount = 0
  const knownNodeTypes = new Set(Object.keys(HR_NODE_DEFS))
  knownNodeTypes.add("sequence_end")

  function validateNode(node: any, depth: number, visited: Set<string>) {
    if (!node || typeof node !== "object") {
      errors.push(`Invalid node encountered at depth ${depth}.`)
      return
    }

    totalNodesCount++
    if (totalNodesCount > 300) {
      errors.push("Safety limit exceeded: blueprint contains more than 300 nodes.")
      return
    }

    if (depth > 50) {
      errors.push("Safety limit exceeded: sequence nesting exceeds 50 levels.")
      return
    }

    if (!node.id || typeof node.id !== "string") {
      errors.push(`Node missing valid ID at depth ${depth}.`)
    } else {
      if (visited.has(node.id)) {
        errors.push(`Cyclic graph detected at node ID '${node.id}'. Blueprints must be acyclic DAGs.`)
        return
      }
      visited.add(node.id)
    }

    if (!node.type || !knownNodeTypes.has(node.type)) {
      warnings.push(`Unrecognized node type '${node.type}'. It will be rendered as generic custom step.`)
    }

    if (node.children && typeof node.children === "object") {
      for (const [branchKey, branch] of Object.entries(node.children)) {
        if (!Array.isArray(branch)) {
          errors.push(`Branch '${branchKey}' of node '${node.id}' must be an array.`)
        } else {
          for (const child of branch) {
            validateNode(child, depth + 1, new Set(visited))
          }
        }
      }
    }
  }

  for (const root of rootNodes) {
    validateNode(root, 1, new Set())
  }

  const stats = calculateBlueprintStats(rootNodes, stickyNotes)

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    stats,
    parsedBlueprint: errors.length === 0 ? (data as EleInBlueprint) : null,
  }
}

// ─── Prepare Import Nodes (Replace or Append) ────────────────────────────────
export function prepareImportNodes(
  blueprint: EleInBlueprint,
  existingRoots: SeqTreeNode[],
  existingNotes: StickyNote[],
  mode: ImportMode
): { nodes: SeqTreeNode[]; stickyNotes: StickyNote[] } {
  const idMap = new Map<string, string>()

  function remapNode(node: SeqTreeNode): SeqTreeNode {
    const newId = uuidv4()
    idMap.set(node.id, newId)

    const newChildren: Record<string, SeqTreeNode[]> = {}
    if (node.children) {
      for (const [branchKey, branch] of Object.entries(node.children)) {
        newChildren[branchKey] = Array.isArray(branch)
          ? branch.map(child => remapNode(child))
          : []
      }
    }

    return {
      ...node,
      id: newId,
      data: deepSanitizeValue(node.data) as Record<string, any>,
      children: newChildren,
    }
  }

  const rawImportRoots = blueprint.sequence.rootNodes || []
  const rawImportNotes = blueprint.sequence.stickyNotes || []

  const remappedRoots = rawImportRoots.map(r => remapNode(r))

  let offsetX = 0
  let offsetY = 0

  if (mode === "append" && existingRoots.length > 0) {
    offsetX = 360
    offsetY = 40
  }

  const remappedNotes: StickyNote[] = rawImportNotes.map(sn => ({
    ...sn,
    id: uuidv4(),
    text: String(deepSanitizeValue(sn.text) || ""),
    title: sn.title ? String(deepSanitizeValue(sn.title)) : undefined,
    x: sn.x + offsetX,
    y: sn.y + offsetY,
  }))

  if (mode === "replace") {
    return {
      nodes: remappedRoots,
      stickyNotes: remappedNotes,
    }
  }

  // Layer 0 & 2 Paranoia: Seamlessly stitch imported roots to existing sequence leaves
  // rather than appending disconnected parallel roots that break visual DAG hierarchy
  const stitchedNodes = stitchSequenceToTree(existingRoots, remappedRoots)

  return {
    nodes: stitchedNodes,
    stickyNotes: [...existingNotes, ...remappedNotes],
  }
}

// ─── Stitch Sequence to Existing Tree Leaves (Layer 0 & 2 Paranoia) ─────────
export function stitchSequenceToTree(
  existingRoots: SeqTreeNode[],
  importedRoots: SeqTreeNode[]
): SeqTreeNode[] {
  if (!existingRoots || existingRoots.length === 0) return importedRoots || []
  if (!importedRoots || importedRoots.length === 0) return existingRoots

  // Deep clone to prevent reference leaks and unintended mutations
  const clonedRoots: SeqTreeNode[] = JSON.parse(JSON.stringify(existingRoots))

  function attachToLeaf(node: SeqTreeNode): boolean {
    const outputs = (HR_NODE_DEFS as any)[node.type]?.outputs || node.data?.outputs
    const isCondition = outputs && outputs.length > 1

    if (isCondition) {
      const primaryLabel = outputs[0] || "then"
      const branchNodes = node.children?.[primaryLabel] || []
      if (branchNodes.length === 0) {
        if (!node.children) node.children = {}
        node.children[primaryLabel] = importedRoots
        return true
      }
      const lastBranchNode = branchNodes[branchNodes.length - 1]
      if (lastBranchNode.type === "sequence_end") {
        branchNodes.splice(branchNodes.length - 1, 1, ...importedRoots)
        return true
      }
      return attachToLeaf(lastBranchNode)
    }

    // Paranoia Layer 1 (FLAW-FE-05): Check both 'output' and 'then' to prevent creating duplicate phantom branches
    const primarySingleKey = (node.children && ("output" in node.children)) ? "output" : "then"
    const existingBranchKey = node.children ? (Object.keys(node.children).find(k => k === "output" || k === "then") || primarySingleKey) : primarySingleKey
    const branchChildren = node.children?.[existingBranchKey] || []
    
    if (branchChildren.length === 0) {
      if (!node.children) node.children = {}
      node.children[existingBranchKey] = importedRoots
      return true
    }

    const lastChild = branchChildren[branchChildren.length - 1]
    if (lastChild.type === "sequence_end") {
      branchChildren.splice(branchChildren.length - 1, 1, ...importedRoots)
      return true
    }

    return attachToLeaf(lastChild)
  }

  const targetRoot = clonedRoots[clonedRoots.length - 1]
  if (targetRoot.type === "sequence_end") {
    clonedRoots.splice(clonedRoots.length - 1, 1, ...importedRoots)
  } else {
    const attached = attachToLeaf(targetRoot)
    if (!attached) {
      return [...clonedRoots, ...importedRoots]
    }
  }

  return clonedRoots
}

// ─── Canvas Rollback Vault (Layer 2 Paranoia) ────────────────────────────────
export interface CanvasSnapshot {
  id: string
  timestamp: string
  formattedTime: string
  label: string
  nodeCount: number
  stickyNotesCount: number
  nodes: SeqTreeNode[]
  stickyNotes: StickyNote[]
}

const VAULT_STORAGE_KEY = "elein_canvas_snapshots_vault"
const MAX_VAULT_SNAPSHOTS = 5

export function getCanvasSnapshots(): CanvasSnapshot[] {
  try {
    const raw = localStorage.getItem(VAULT_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveCanvasSnapshot(
  nodes: SeqTreeNode[],
  stickyNotes: StickyNote[],
  label = "Pre-Import Canvas Snapshot"
): CanvasSnapshot {
  const snapshots = getCanvasSnapshots()
  const now = new Date()
  const newSnapshot: CanvasSnapshot = {
    id: uuidv4(),
    timestamp: now.toISOString(),
    formattedTime: now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    label,
    nodeCount: nodes.length,
    stickyNotesCount: stickyNotes.length,
    nodes: JSON.parse(JSON.stringify(nodes)),
    stickyNotes: JSON.parse(JSON.stringify(stickyNotes)),
  }

  const updated = [newSnapshot, ...snapshots].slice(0, MAX_VAULT_SNAPSHOTS)
  try {
    localStorage.setItem(VAULT_STORAGE_KEY, JSON.stringify(updated))
  } catch (e) {
    console.warn("[Rollback Vault] Failed to persist snapshot to localStorage", e)
  }
  return newSnapshot
}

export function restoreCanvasSnapshot(snapshotId: string): CanvasSnapshot | null {
  const snapshots = getCanvasSnapshots()
  return snapshots.find(s => s.id === snapshotId) || null
}

export function deleteCanvasSnapshot(snapshotId: string): void {
  const snapshots = getCanvasSnapshots().filter(s => s.id !== snapshotId)
  localStorage.setItem(VAULT_STORAGE_KEY, JSON.stringify(snapshots))
}

export function clearCanvasSnapshots(): void {
  localStorage.removeItem(VAULT_STORAGE_KEY)
}

// ─── File Format Sniffer & Auto-Repair (Layer 2 Human Paranoia) ──────────────
export type SniffedFileType = "blueprint" | "leads_csv" | "image" | "unknown"

export interface SniffedFileResult {
  type: SniffedFileType
  name: string
  size: number
  mime: string
  previewText?: string
  guidance?: string
  rawContent?: string
}

export async function sniffDroppedFile(file: File): Promise<SniffedFileResult> {
  const lowerName = file.name.toLowerCase()
  const mime = file.type || ""

  // 1. Leads CSV or Spreadsheet
  if (
    lowerName.endsWith(".csv") ||
    lowerName.endsWith(".tsv") ||
    lowerName.endsWith(".xlsx") ||
    mime.includes("csv") ||
    mime.includes("spreadsheet")
  ) {
    return {
      type: "leads_csv",
      name: file.name,
      size: file.size,
      mime,
      guidance: "This file is a Lead List / Spreadsheet, not a sequence workflow blueprint.",
    }
  }

  // 2. Images
  if (
    lowerName.endsWith(".png") ||
    lowerName.endsWith(".jpg") ||
    lowerName.endsWith(".jpeg") ||
    lowerName.endsWith(".svg") ||
    lowerName.endsWith(".webp") ||
    mime.startsWith("image/")
  ) {
    return {
      type: "image",
      name: file.name,
      size: file.size,
      mime,
      guidance: "Image file detected. Ele-in accepts .elein and .json workflow blueprints on the canvas.",
    }
  }

  // 3. Potential Blueprint (.elein or .json)
  if (lowerName.endsWith(".elein") || lowerName.endsWith(".json") || mime === "application/json") {
    try {
      const text = await file.text()
      return {
        type: "blueprint",
        name: file.name,
        size: file.size,
        mime,
        rawContent: text,
      }
    } catch {
      return {
        type: "unknown",
        name: file.name,
        size: file.size,
        mime,
        guidance: "Failed to read text contents from dropped file.",
      }
    }
  }

  return {
    type: "unknown",
    name: file.name,
    size: file.size,
    mime,
    guidance: "Unsupported file format. Please drop a valid .elein or .json blueprint file.",
  }
}

// ─── Partial / Truncated JSON Auto-Repair ─────────────────────────────────────
export function repairTruncatedJson(jsonStr: string): string {
  let str = jsonStr.trim()
  if (!str) return str

  let inString = false
  let escaped = false
  const stack: string[] = []

  for (let i = 0; i < str.length; i++) {
    const char = str[i]
    if (escaped) {
      escaped = false
      continue
    }
    if (char === "\\") {
      escaped = true
      continue
    }
    if (char === '"') {
      inString = !inString
      continue
    }
    if (!inString) {
      if (char === "{" || char === "[") {
        stack.push(char)
      } else if (char === "}") {
        if (stack.length > 0 && stack[stack.length - 1] === "{") stack.pop()
      } else if (char === "]") {
        if (stack.length > 0 && stack[stack.length - 1] === "[") stack.pop()
      }
    }
  }

  if (inString) {
    str += '"'
  }

  str = str.replace(/,\s*$/, "")

  while (stack.length > 0) {
    const openBracket = stack.pop()
    if (openBracket === "{") str += "}"
    if (openBracket === "[") str += "]"
  }

  return str
}

// ─── Download and Clipboard Helpers ──────────────────────────────────────────
export function downloadBlueprintFile(blueprint: EleInBlueprint, customFilename?: string): void {
  const cleanName = (customFilename || blueprint.metadata.name || "elein_workflow")
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "_")
    .replace(/_+/g, "_")

  const filename = cleanName.endsWith(".elein") ? cleanName : `${cleanName}.elein`
  const jsonContent = JSON.stringify(blueprint, null, 2)
  const blob = new Blob([jsonContent], { type: "application/json" })
  const url = URL.createObjectURL(blob)

  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function copyBlueprintToClipboard(blueprint: EleInBlueprint): Promise<boolean> {
  try {
    const jsonStr = JSON.stringify(blueprint, null, 2)
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(jsonStr)
      return true
    }
    return false
  } catch {
    return false
  }
}

export async function parseBlueprintFile(file: File): Promise<EleInBlueprint> {
  const sniffed = await sniffDroppedFile(file)
  if (sniffed.type !== "blueprint" || !sniffed.rawContent) {
    throw new Error(sniffed.guidance || "Not a valid blueprint file.")
  }

  let parsed: any
  try {
    parsed = JSON.parse(sniffed.rawContent)
  } catch (firstErr: any) {
    try {
      const repaired = repairTruncatedJson(sniffed.rawContent)
      parsed = JSON.parse(repaired)
    } catch {
      throw new Error(`JSON Syntax Error: ${firstErr.message}. Ensure the file was not cut off.`)
    }
  }

  const validation = validateBlueprint(parsed)
  if (!validation.isValid) {
    throw new Error(validation.errors.join("\n"))
  }
  return validation.parsedBlueprint!
}

export function parseBlueprintJsonString(jsonStr: string): EleInBlueprint {
  let parsed: any
  try {
    parsed = JSON.parse(jsonStr)
  } catch (firstErr: any) {
    try {
      const repaired = repairTruncatedJson(jsonStr)
      parsed = JSON.parse(repaired)
    } catch {
      throw new Error(`JSON Syntax Error: ${firstErr.message}. Verify trailing brackets.`)
    }
  }

  const validation = validateBlueprint(parsed)
  if (!validation.isValid) {
    throw new Error(validation.errors.join("\n"))
  }
  return validation.parsedBlueprint!
}
