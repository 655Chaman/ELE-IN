import { create } from "zustand"
import { persist } from "zustand/middleware"
import { addEdge, applyNodeChanges, applyEdgeChanges } from "@xyflow/react"
import type { Node, Edge, Connection, NodeChange, EdgeChange } from "@xyflow/react"

export interface EISequenceStore {
  nodes: Node[]
  edges: Edge[]
  selectedNodeId: string | null

  // Canvas
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (node: Node) => void
  deleteNode: (nodeId: string) => void
  selectNode: (id: string | null) => void
  updateNodeData: (nodeId: string, data: Record<string, any>) => void

  // Reset
  reset: () => void
  loadFromDefinition: (def: { nodes: any[]; edges: any[] }) => void
}

export const useHRSequenceStore = create<EISequenceStore>()(
  persist(
    (set) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  onNodesChange: (changes) =>
    set((s) => ({ nodes: applyNodeChanges(changes, s.nodes) })),

  onEdgesChange: (changes) =>
    set((s) => ({ edges: applyEdgeChanges(changes, s.edges) })),

  onConnect: (connection) =>
    set((s) => ({
      edges: addEdge(
        {
          ...connection,
          animated: false,
          style: { stroke: "#6366f1", strokeWidth: 2 },
          label: "",
          labelStyle: { fill: "#a1a1aa", fontSize: 10 },
          labelBgStyle: { fill: "#18181b" },
        },
        s.edges
      ),
    })),

  addNode: (node) => set((s) => ({ nodes: [...s.nodes, node] })),

  deleteNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
    })),

  selectNode: (id) => set({ selectedNodeId: id }),

  updateNodeData: (nodeId, data) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
    })),

  reset: () => set({ nodes: [], edges: [], selectedNodeId: null }),

  loadFromDefinition: (def) => {
    const nodes: Node[] = (def.nodes || []).map((n: any) => ({
      id: n.id,
      type: n.type || "eiNode",
      position: n.position,
      data: n.data || {},
    }))
    const edges: Edge[] = (def.edges || []).map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle,
      targetHandle: e.targetHandle,
      label: e.label || "",
      animated: false,
      style: { stroke: "#6366f1", strokeWidth: 2 },
      labelStyle: { fill: "#a1a1aa", fontSize: 10 },
      labelBgStyle: { fill: "#18181b" },
    }))
    set({ nodes, edges, selectedNodeId: null })
  },
}), { name: "elein-sequence-storage" }))
