import type { EINodeType } from "@/lib/eiNodeDefs";
import { create } from "zustand"
import { persist } from "zustand/middleware"
import { v4 as uuidv4 } from "uuid"

export interface StickyNote {
  id: string;
  x: number;
  y: number;
  text: string;
  color?: string;
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
  
  addStickyNote: (x: number, y: number) => void
  updateStickyNote: (id: string, text: string) => void
  removeStickyNote: (id: string) => void
  moveStickyNote: (id: string, x: number, y: number) => void
  changeStickyNoteColor: (id: string, color: string) => void
  
  addRoot: (type: EINodeType | "sequence_end", data?: Record<string, any>) => void
  addChild: (parentId: string, branchLabel: string, type: EINodeType | "sequence_end", data?: Record<string, any>) => void
  endBranch: (parentId: string, branchLabel: string) => void
  removeNode: (nodeId: string) => void
  duplicateNode: (nodeId: string) => void

  updateNodeData: (nodeId: string, patch: Record<string, any>) => void
  moveNodeInBranch: (parentId: string | null, branchLabel: string, dragIndex: number, dropIndex: number) => void
  selectNode: (id: string | null) => void
  reset: () => void
  loadTree: (rootNodes: SeqTreeNode[], stickyNotes?: StickyNote[]) => void
  undo: () => void
  redo: () => void
}

function makeNode(type: EINodeType | "sequence_end", data?: Record<string, any>): SeqTreeNode {
  const outputs = data?.outputs as string[] | undefined
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

export const useHRTreeStore = create<EITreeStore>()(persist((set) => ({
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

  addStickyNote: (x, y) => set(state => {
    const id = uuidv4()
    const newNote: StickyNote = { id, x, y, text: "", color: "bg-warning/20" }
    return { stickyNotes: [...state.stickyNotes, newNote] }
  }),
  
  updateStickyNote: (id, text) => set(state => {
    return {
      stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, text } : sn)
    }
  }),
  
  removeStickyNote: (id) => set(state => {
    return {
      stickyNotes: state.stickyNotes.filter(sn => sn.id !== id)
    }
  }),
  
  moveStickyNote: (id, x, y) => set(state => {
    return {
      stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, x, y } : sn)
    }
  }),
  
  changeStickyNoteColor: (id, color) => set(state => {
    return {
      stickyNotes: state.stickyNotes.map(sn => sn.id === id ? { ...sn, color } : sn)
    }
  }),

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
  
  loadTree: (rootNodes, stickyNotes) => set({ rootNodes, stickyNotes: stickyNotes || [], selectedNodeId: null, history: [], future: [] }),

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
}), {
  name: 'hr-tree-store',
  partialize: (state) => ({ rootNodes: state.rootNodes, stickyNotes: state.stickyNotes, formState: state.formState, campaignStep: state.campaignStep })
}))


export function dagToTree(nodes: any[], edges: any[]): SeqTreeNode[] {
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

  function buildTree(nodeId: string, visited: Set<string>): SeqTreeNode | null {
    if (visited.has(nodeId)) return null; // cycle guard
    visited.add(nodeId);

    const n = nodeMap.get(nodeId);
    if (!n) {
      visited.delete(nodeId);
      return null;
    }

    const outputs = n.data?.outputs as string[] | undefined;
    const labels = outputs && outputs.length > 1 ? outputs : (n.type === "sequence_end" ? [] : ["output"]);
    const children: Record<string, SeqTreeNode[]> = {};
    labels.forEach(label => {
      children[label] = [];
    });

    const targets = childrenMap.get(nodeId) || [];
    targets.forEach(t => {
      if (!children[t.handle]) children[t.handle] = [];
      const childNode = buildTree(t.target, visited);
      if (childNode) {
        children[t.handle].push(childNode);
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

  const rootIds = nodes.filter(n => inDegree.get(n.id) === 0).map(n => n.id);
  const roots: SeqTreeNode[] = [];
  
  rootIds.forEach(id => {
    const root = buildTree(id, new Set<string>());
    if (root) roots.push(root);
  });
  
  return roots;
}

export function treeToDag(roots: SeqTreeNode[]): { nodes: any[], edges: any[] } {
  const nodes: any[] = []
  const edges: any[] = []
  const visited = new Set<string>()

  function traverse(node: SeqTreeNode) {
    if (visited.has(node.id)) return
    visited.add(node.id)

    nodes.push({
      id: node.id,
      type: node.type,
      data: node.data,
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

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === 'hr-tree-store') {
      useHRTreeStore.persist.rehydrate();
    }
  });
}
