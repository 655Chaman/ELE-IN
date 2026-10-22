import { HR_NODE_DEFS, type EINodeType } from "@/lib/eiNodeDefs";
import { create } from "zustand"
import { v4 as uuidv4 } from "uuid"

export interface StickyNote {
  id: string;
  x: number;
  y: number;
  text: string;
  title?: string;
  color?: string;
  category?: "note" | "todo" | "warning" | "strategy" | "handover";
  isPinned?: boolean;
  isCollapsed?: boolean;
  updatedAt?: string;
}

export interface SeqTreeNode {
  id: string
  type: EINodeType | "sequence_end"
  data: Record<string, any>
  children: Record<string, SeqTreeNode[]>
  branchEnded?: boolean
}

export interface EITreeStore {
  rootNodes: SeqTreeNode[]
  stickyNotes: StickyNote[]
  selectedNodeId: string | null
  history: SeqTreeNode[][]
  future: SeqTreeNode[][]
  formState: Record<string, any>
  campaignStep: number
  setFormState: (state: Record<string, any>) => void
  setCampaignStep: (step: number) => void
  
  addStickyNote: (x: number, y: number, color?: string, category?: string) => string
  updateStickyNote: (id: string, text: string) => void
  updateStickyNoteFull: (id: string, patch: Partial<StickyNote>) => void
  removeStickyNote: (id: string) => void
  moveStickyNote: (id: string, x: number, y: number) => void
  changeStickyNoteColor: (id: string, color: string) => void
  toggleStickyNoteCollapse: (id: string) => void
  toggleStickyNotePin: (id: string) => void
  
  addRoot: (type: EINodeType | "sequence_end", data?: Record<string, any>) => void
  addChild: (parentId: string, branchLabel: string, type: EINodeType | "sequence_end", data?: Record<string, any>) => void
  endBranch: (parentId: string, branchLabel: string) => void
  removeNode: (nodeId: string) => void
  duplicateNode: (nodeId: string) => void

  updateNodeData: (nodeId: string, patch: Record<string, any>) => void
  moveNodeInBranch: (parentId: string | null, branchLabel: string, dragIndex: number, dropIndex: number) => void
  selectNode: (id: string | null) => void
  reset: () => void
  loadTree: (rootNodes: SeqTreeNode[], stickyNotes?: StickyNote[], options?: { preserveHistory?: boolean }) => void
  undo: () => void
  redo: () => void
}

function makeNode(type: EINodeType | "sequence_end", data?: Record<string, any>): SeqTreeNode {
  const def = (HR_NODE_DEFS as any)?.[type]
  const outputs = (data?.outputs as string[] | undefined) || (def?.outputs as string[] | undefined)
  const labels = outputs && outputs.length > 0 ? outputs : (type === "sequence_end" ? [] : ["output"])
  const branches: Record<string, SeqTreeNode[]> = {}
  for (const label of labels) branches[label] = []
  return { id: uuidv4(), type, data: data || {}, children: branches }
}

function updateInTree(
  nodes: SeqTreeNode[],
  nodeId: string,
  updater: (n: SeqTreeNode) => SeqTreeNode
): SeqTreeNode[] {
  return nodes.map(n => {
    if (n.id === nodeId) return updater(n)
    const newChildren: Record<string, SeqTreeNode[]> = {}
    for (const [k, v] of Object.entries(n.children || {}))
      newChildren[k] = updateInTree(v, nodeId, updater)
    return { ...n, children: newChildren }
  })
}

function removeFromTree(nodes: SeqTreeNode[], nodeId: string): SeqTreeNode[] {
  return nodes
    .filter(n => n.id !== nodeId)
    .map(n => {
      const newChildren: Record<string, SeqTreeNode[]> = {}
      for (const [k, v] of Object.entries(n.children || {}))
        newChildren[k] = removeFromTree(v, nodeId)
      return { ...n, children: newChildren }
    })
}

export const useHRTreeStore = create<EITreeStore>()((set) => ({
  rootNodes: [],
  stickyNotes: [],
  selectedNodeId: null,
  history: [],
  future: [],
  formState: {
    campaignName: '',
    senders: [],
    senderIds: [],
    leads: [],
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    schedule: {},
    limit: 50,
    provider: 'any',
    leadListId: '',
    excludeListId: ''
  },
  campaignStep: 0,
  
  setFormState: (formState) => set({ formState }),
  setCampaignStep: (campaignStep) => set({ campaignStep }),

  addStickyNote: (x, y, color = "amber", category = "note") => {
    const id = uuidv4()
    const newNote: StickyNote = {
      id,
      x: Math.round(x),
      y: Math.round(y),
      text: "",
      title: "",
      color,
      category: category as any,
      isPinned: false,
      isCollapsed: false,
      updatedAt: new Date().toISOString()
    }
    set(state => ({ stickyNotes: [...state.stickyNotes, newNote] }))
    return id
  },
  
  updateStickyNote: (id, text) => set(state => ({
    stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, text, updatedAt: new Date().toISOString() } : sn)
  })),

  updateStickyNoteFull: (id, patch) => set(state => ({
    stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, ...patch, updatedAt: new Date().toISOString() } : sn)
  })),
  
  removeStickyNote: (id) => set(state => ({
    stickyNotes: state.stickyNotes.filter(sn => sn.id !== id)
  })),
  
  moveStickyNote: (id, x, y) => set(state => ({
    stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, x: Math.round(x), y: Math.round(y) } : sn)
  })),
  
  changeStickyNoteColor: (id, color) => set(state => ({
    stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, color } : sn)
  })),

  toggleStickyNoteCollapse: (id) => set(state => ({
    stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, isCollapsed: !sn.isCollapsed } : sn)
  })),

  toggleStickyNotePin: (id) => set(state => ({
    stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, isPinned: !sn.isPinned } : sn)
  })),

  addRoot: (type, data) =>
    set(s => ({
      history: [...s.history, s.rootNodes],
      future: [],
      rootNodes: [...s.rootNodes, makeNode(type, data)]
    })),

  addChild: (parentId, branchLabel, type, data) =>
    set(s => ({
      history: [...s.history, s.rootNodes],
      future: [],
      rootNodes: updateInTree(s.rootNodes, parentId, n => ({
        ...n,
        children: {
          ...n.children,
          [branchLabel]: [...(n.children[branchLabel] || []), makeNode(type, data)],
        },
      })),
    })),

  endBranch: (parentId, branchLabel) =>
    set(s => ({
      history: [...s.history, s.rootNodes],
      future: [],
      rootNodes: updateInTree(s.rootNodes, parentId, n => ({
        ...n,
        children: {
          ...n.children,
          [branchLabel]: [
            ...(n.children[branchLabel] || []),
            makeNode("sequence_end", { label: "End sequence", outputs: [] }),
          ],
        },
      })),
    })),


  duplicateNode: (nodeId) =>
    set(s => {
      // Find the node and its path
      let targetNode: any = null;
      let targetParentId: string | null = null;
      let targetBranchLabel: string | null = null;
      let targetIndex: number = -1;

      const searchArray = (nodes: any[], parentId: string | null, branchLabel: string | null) => {
        for (let i = 0; i < nodes.length; i++) {
          if (nodes[i].id === nodeId) {
            targetNode = nodes[i];
            targetParentId = parentId;
            targetBranchLabel = branchLabel;
            targetIndex = i;
            return true;
          }
          for (const [bl, children] of Object.entries(nodes[i].children || {})) {
            if (searchArray(children as any[], nodes[i].id, bl)) return true;
          }
        }
        return false;
      };

      searchArray(s.rootNodes, null, null);

      if (!targetNode) return {};

      const duplicateDeep = (node: any): any => {
        const newNode = {
          id: uuidv4(),
          type: node.type,
          data: JSON.parse(JSON.stringify(node.data)),
          children: {} as Record<string, any[]>
        };
        for (const [branch, children] of Object.entries(node.children || {})) {
          newNode.children[branch] = (children as any[]).map(duplicateDeep);
        }
        return newNode;
      };

      const newNode = duplicateDeep(targetNode);

      if (targetParentId === null || targetBranchLabel === null) {
        const newRootNodes = [...s.rootNodes];
        newRootNodes.splice(targetIndex + 1, 0, newNode);
        return {
          history: [...s.history, s.rootNodes],
          future: [],
          rootNodes: newRootNodes
        };
      }

      return {
        history: [...s.history, s.rootNodes],
        future: [],
        rootNodes: updateInTree(s.rootNodes, targetParentId, n => {
          const arr = [...(n.children[targetBranchLabel as string] || [])];
          arr.splice(targetIndex + 1, 0, newNode);
          return {
            ...n,
            children: {
              ...n.children,
              [targetBranchLabel as string]: arr
            }
          };
        })
      };
    }),

  removeNode: (nodeId) =>
    set(s => ({
      history: [...s.history, s.rootNodes],
      future: [],
      rootNodes: removeFromTree(s.rootNodes, nodeId),
      selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
    })),

  updateNodeData: (nodeId, patch) =>
    set(s => ({
      history: [...s.history, s.rootNodes],
      future: [],
      rootNodes: updateInTree(s.rootNodes, nodeId, n => ({
        ...n, data: { ...n.data, ...patch },
      })),
    })),

  moveNodeInBranch: (parentId, branchLabel, dragIndex, dropIndex) =>
    set(s => {
      if (dragIndex === dropIndex) return {}
      
      const doReorder = (nodes: SeqTreeNode[]): SeqTreeNode[] => {
        const result = Array.from(nodes)
        const [removed] = result.splice(dragIndex, 1)
        result.splice(dropIndex, 0, removed)
        return result
      }
      
      if (!parentId) {
        return {
          history: [...s.history, s.rootNodes],
          future: [],
          rootNodes: doReorder(s.rootNodes)
        }
      }
      
      return {
        history: [...s.history, s.rootNodes],
        future: [],
        rootNodes: updateInTree(s.rootNodes, parentId, n => ({
          ...n,
          children: {
            ...n.children,
            [branchLabel]: doReorder(n.children[branchLabel] || [])
          }
        }))
      }
    }),

  selectNode: (id) => set({ selectedNodeId: id }),
  
  reset: () => set({ rootNodes: [], stickyNotes: [], selectedNodeId: null, history: [], future: [], formState: { campaignName: '', senders: [], senderIds: [], leads: [], timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', schedule: {}, limit: 50, provider: 'any', leadListId: '', excludeListId: '' }, campaignStep: 0 }),
  
  // Paranoia Layer 0 & 2 (FLAW-FE-19): Preserve existing canvas in history when importing/loading a tree
  loadTree: (rootNodes, stickyNotes, options) => set(s => {
    const shouldPreserve = options?.preserveHistory ?? (s.rootNodes && s.rootNodes.length > 0);
    return {
      rootNodes,
      stickyNotes: stickyNotes || [],
      selectedNodeId: null,
      history: shouldPreserve ? [...s.history.slice(-19), s.rootNodes] : [],
      future: [],
    };
  }),

  undo: () => set(s => {
    if (s.history.length === 0) return {}
    const previous = s.history[s.history.length - 1]
    const newHistory = s.history.slice(0, -1)
    return {
      history: newHistory,
      future: [s.rootNodes, ...s.future],
      rootNodes: previous
    }
  }),

  redo: () => set(s => {
    if (s.future.length === 0) return {}
    const next = s.future[0]
    const newFuture = s.future.slice(1)
    return {
      history: [...s.history, s.rootNodes],
      future: newFuture,
      rootNodes: next
    }
  })
}))



export interface DagToTreeOptions {
  onCycleDetected?: (cycleNodes: string[]) => void
}

export function hasDagCycles(nodes: any[], edges: any[]): boolean {
  if (!nodes || nodes.length === 0) return false
  const inDegree = new Map<string, number>()
  nodes.forEach(n => inDegree.set(n.id, 0))
  edges.forEach(e => {
    inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1)
  })

  const queue: string[] = []
  nodes.forEach(n => {
    if ((inDegree.get(n.id) || 0) === 0) queue.push(n.id)
  })

  let count = 0
  const adj = new Map<string, string[]>()
  edges.forEach(e => {
    const list = adj.get(e.source) || []
    list.push(e.target)
    adj.set(e.source, list)
  })

  while (queue.length > 0) {
    const u = queue.shift()!
    count++
    for (const v of adj.get(u) || []) {
      const newDeg = (inDegree.get(v) || 0) - 1
      inDegree.set(v, newDeg)
      if (newDeg === 0) queue.push(v)
    }
  }

  return count !== nodes.length
}

export function dagToTree(nodes: any[], edges: any[], options?: DagToTreeOptions): SeqTreeNode[] {
  const nodeMap = new Map<string, any>()
  nodes.forEach(n => nodeMap.set(n.id, n))

  const childrenMap = new Map<string, Array<{target: string, handle: string}>>()
  edges.forEach(e => {
    const list = childrenMap.get(e.source) || []
    list.push({ target: e.target, handle: e.sourceHandle || "output" })
    childrenMap.set(e.source, list)
  })

  const inDegree = new Map<string, number>()
  nodes.forEach(n => inDegree.set(n.id, 0))
  edges.forEach(e => {
    inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1)
  })

  let detectedCycles = false
  const cycleNodes = new Set<string>()

  function buildTree(nodeId: string, visited: Set<string>): SeqTreeNode | null {
    if (visited.has(nodeId)) {
      detectedCycles = true
      cycleNodes.add(nodeId)
      return null; // cycle guard
    }
    visited.add(nodeId);

    const n = nodeMap.get(nodeId);
    if (!n) {
      visited.delete(nodeId);
      return null;
    }

    const def = (HR_NODE_DEFS as any)?.[n.type];
    const outputs = (n.data?.outputs as string[] | undefined) || (def?.outputs as string[] | undefined);
    const labels = outputs && outputs.length > 0 ? outputs : (n.type === "sequence_end" ? [] : ["output"]);
    const children: Record<string, SeqTreeNode[]> = {};
    labels.forEach(label => {
      children[label] = [];
    });

    const targets = childrenMap.get(nodeId) || [];
    targets.forEach(t => {
      let targetHandle = t.handle;
      // Normalization: handle mismatch between "output", "then", and defined labels
      if (!children[targetHandle]) {
        const matchingLabel = labels.find(l => l.toLowerCase() === (targetHandle || "").toLowerCase());
        if (matchingLabel) {
          targetHandle = matchingLabel;
        } else if (labels.length === 1) {
          targetHandle = labels[0];
        } else if (targetHandle === "output" && children["then"]) {
          targetHandle = "then";
        } else if (targetHandle === "then" && children["output"]) {
          targetHandle = "output";
        } else if (children[labels[0]] && (targetHandle === "then" || targetHandle === "output" || targets.length === 1)) {
          // If edge uses generic "then"/"output" on a multi-output node or is the single outgoing edge,
          // route to the primary branch (labels[0], e.g. "Accepted") rather than spawning a phantom 3rd branch.
          targetHandle = labels[0];
        }
      }
      if (!children[targetHandle]) children[targetHandle] = [];
      const childNode = buildTree(t.target, visited);
      if (childNode) {
        children[targetHandle].push(childNode);
      }
    });

    visited.delete(nodeId);

    return {
      id: n.id,
      type: n.type,
      data: n.data,
      children
    };
  }

  // Find nodes with inDegree 0
  let rootIds = nodes.filter(n => (inDegree.get(n.id) || 0) === 0).map(n => n.id);

  // Paranoia Layer 1 & 2 (UI-04): If graph has a cycle such that every node has inDegree > 0,
  // do NOT wipe out the entire sequence! Pick the most likely entry node (e.g. trigger node,
  // or node with lowest inDegree, or nodes[0]).
  if (rootIds.length === 0 && nodes.length > 0) {
    detectedCycles = true
    const triggerNode = nodes.find(n => n.type === "trigger" || n.type === "sequence_start");
    if (triggerNode) {
      rootIds = [triggerNode.id];
    } else {
      let minNode = nodes[0];
      let minIn = inDegree.get(minNode.id) ?? 999;
      for (const n of nodes) {
        const d = inDegree.get(n.id) ?? 0;
        if (d < minIn) {
          minIn = d;
          minNode = n;
        }
      }
      rootIds = [minNode.id];
    }
  }

  const roots: SeqTreeNode[] = [];
  const processedNodeIds = new Set<string>();

  rootIds.forEach(id => {
    const root = buildTree(id, new Set<string>());
    if (root) {
      roots.push(root);
      const markVisited = (node: SeqTreeNode) => {
        processedNodeIds.add(node.id);
        Object.values(node.children || {}).forEach(branch => branch.forEach(markVisited));
      };
      markVisited(root);
    }
  });

  // Layer 1 Environmental Paranoia: If any disconnected nodes or unattached island nodes remain,
  // recover them as roots instead of silently dropping them!
  nodes.forEach(n => {
    if (!processedNodeIds.has(n.id)) {
      const recovered = buildTree(n.id, new Set<string>());
      if (recovered) {
        roots.push(recovered);
        const markVisited = (node: SeqTreeNode) => {
          processedNodeIds.add(node.id);
          Object.values(node.children || {}).forEach(branch => branch.forEach(markVisited));
        };
        markVisited(recovered);
      }
    }
  });

  if (detectedCycles && options?.onCycleDetected) {
    options.onCycleDetected(Array.from(cycleNodes));
  }

  return roots;
}

export function treeToDag(roots: SeqTreeNode[]): { nodes: any[], edges: any[] } {
  const nodes: any[] = []
  const edges: any[] = []
  const visited = new Set<string>()

  function traverse(node: SeqTreeNode) {
    if (visited.has(node.id)) return
    visited.add(node.id)

    const cleanData = { ...(node.data || {}) }
    // Paranoia Layer 0, 1 & 2 (UI-17 & AUDIT-01): Allow valid 0-delay (immediate action) while guarding against null, NaN, negative, or Infinity
    if ("delay_hours" in cleanData || (node.type as string) === "delay" || String(node.type).includes("delay")) {
      const raw = cleanData.delay_hours
      if (raw !== undefined && raw !== null && raw !== "") {
        const num = Number(raw)
        cleanData.delay_hours = (!isNaN(num) && isFinite(num) && num >= 0) ? Math.max(0, Math.ceil(num)) : 24
      } else if ((node.type as string) === "delay" || String(node.type).includes("delay")) {
        cleanData.delay_hours = 24
      }
    }
    if ("delay_days" in cleanData) {
      const raw = cleanData.delay_days
      if (raw !== undefined && raw !== null && raw !== "") {
        const num = Number(raw)
        cleanData.delay_days = (!isNaN(num) && isFinite(num) && num >= 0) ? Math.max(0, Math.ceil(num)) : 1
      }
    }
    if ("delay_minutes" in cleanData) {
      const raw = cleanData.delay_minutes
      if (raw !== undefined && raw !== null && raw !== "") {
        const num = Number(raw)
        cleanData.delay_minutes = (!isNaN(num) && isFinite(num) && num >= 0) ? Math.max(0, Math.ceil(num)) : 15
      }
    }
    if ("delay" in cleanData) {
      const raw = cleanData.delay
      if (raw !== undefined && raw !== null && raw !== "") {
        const num = Number(raw)
        cleanData.delay = (!isNaN(num) && isFinite(num) && num >= 0) ? Math.max(0, Math.ceil(num)) : (cleanData.delay_hours ?? 24)
      } else {
        cleanData.delay = cleanData.delay_hours ?? 24
      }
    }

    nodes.push({
      id: node.id,
      type: node.type,
      data: cleanData,
      position: { x: 0, y: 0 }
    })

    for (const [handle, children] of Object.entries(node.children || {})) {
      for (const child of children) {
        edges.push({
          id: `e-${node.id}-${child.id}`,
          source: node.id,
          sourceHandle: handle,
          target: child.id
        })
        traverse(child)
      }
    }
  }

  roots.forEach(traverse)
  return { nodes, edges }
}


// LAYER 0 + LAYER 1: Paranoia - Draft Autosave Helper with Environmental Failure Protection (QuotaExceeded)
export function saveDraftToLocalStorage(state: EITreeStore) {
  if (typeof window === "undefined") return
  let draftPayload: any = null
  try {
    const { nodes, edges } = treeToDag(state.rootNodes)
    // Paranoia Layer 2: Guard against saving an empty skeleton over an existing meaningful draft
    if (nodes.length === 0 && (!state.formState?.campaignName || state.formState?.campaignName === 'New Campaign') && !state.formState?.leadListId) {
      return
    }
    draftPayload = {
      nodes,
      edges,
      stickyNotes: state.stickyNotes,
      formState: state.formState,
      step: state.campaignStep,
      timestamp: Date.now()
    }
    localStorage.setItem("elein_unsaved_draft", JSON.stringify(draftPayload))
  } catch (e: any) {
    console.warn("Failed to autosave campaign draft to localStorage:", e)
    // Paranoia Layer 1 & 2 (FLAW-FE-11): Handle QuotaExceededError and notify via window event
    if (e?.name === "QuotaExceededError" || e?.code === 22 || e?.number === -2147024882) {
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i)
          if (key && (key.startsWith("elein_cache_") || key.startsWith("elein_snap_"))) {
            localStorage.removeItem(key)
          }
        }
        if (draftPayload) {
          localStorage.setItem("elein_unsaved_draft", JSON.stringify(draftPayload))
        }
        return
      } catch (retryErr) {
        console.error("LocalStorage quota exceeded even after cache eviction:", retryErr)
      }
      if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
        window.dispatchEvent(new CustomEvent("elein-draft-save-failed", {
          detail: { reason: "Browser storage full (QuotaExceededError). Please free disk space." }
        }))
      }
    }
  }
}

