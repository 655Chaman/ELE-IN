import { create } from "zustand"
import { addEdge, applyNodeChanges, applyEdgeChanges } from "@xyflow/react"
import type { Node, Edge, Connection, NodeChange, EdgeChange } from "@xyflow/react"

export interface WorkflowMeta {
  id: string | null
  name: string
  description: string
  version: number
  isSaved: boolean
  isDirty: boolean
}

export type ExecutionEvent =
  | { type: 'node_start'; nodeId: string; timestamp: number }
  | { type: 'node_complete'; nodeId: string; output: any; duration_s: number; timestamp: number }
  | { type: 'node_error'; nodeId: string; error: string; timestamp: number }
  | { type: 'edge_transfer'; edgeId: string; sourceId: string; targetId: string; data: any; timestamp: number };

export interface RunState {
  runId: string | null
  status: "idle" | "running" | "completed" | "failed" | "stopped"
  nodeStates: Record<string, { status: string; output?: any; error?: string; duration_s?: number }>
  logs: string[]
  history: ExecutionEvent[]
  scrubIndex: number | null
  scrubbedNodeStates: Record<string, { status: string; output?: any; error?: string; duration_s?: number }>
}

interface WorkflowStore {
  nodes: Node[]
  edges: Edge[]
  meta: WorkflowMeta
  run: RunState
  selectedNodeId: string | null

  // Canvas actions
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (node: Node) => void
  updateNodeData: (nodeId: string, data: Record<string, any>) => void
  deleteNode: (nodeId: string) => void
  selectNode: (nodeId: string | null) => void

  // Workflow meta
  setMeta: (meta: Partial<WorkflowMeta>) => void
  loadWorkflow: (wf: any) => void
  markDirty: () => void

  // Run state
  setRunState: (run: Partial<RunState>) => void
  updateNodeRunState: (nodeId: string, state: any) => void
  pushHistoryEvent: (event: ExecutionEvent) => void
  setScrubIndex: (index: number | null) => void
  appendLog: (line: string) => void
  resetRun: () => void
}

const defaultMeta: WorkflowMeta = {
  id: null,
  name: "Untitled Workflow",
  description: "",
  version: 1,
  isSaved: false,
  isDirty: false,
}

const defaultRun: RunState = {
  runId: null,
  status: "idle",
  nodeStates: {},
  logs: [],
  history: [],
  scrubIndex: null,
  scrubbedNodeStates: {},
}

export const useWorkflowStore = create<WorkflowStore>((set) => ({
  nodes: [],
  edges: [],
  meta: { ...defaultMeta },
  run: { ...defaultRun },
  selectedNodeId: null,

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  onNodesChange: (changes) =>
    set((s) => ({ nodes: applyNodeChanges(changes, s.nodes) })),

  onEdgesChange: (changes) =>
    set((s) => ({ edges: applyEdgeChanges(changes, s.edges) })),

  onConnect: (connection) =>
    set((s) => ({
      edges: addEdge({ ...connection, animated: true }, s.edges),
      meta: { ...s.meta, isDirty: true },
    })),

  addNode: (node) =>
    set((s) => ({
      nodes: [...s.nodes, node],
      meta: { ...s.meta, isDirty: true },
    })),

  updateNodeData: (nodeId, data) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
      meta: { ...s.meta, isDirty: true },
    })),

  deleteNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
      meta: { ...s.meta, isDirty: true },
    })),

  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  setMeta: (meta) => set((s) => ({ meta: { ...s.meta, ...meta } })),

  loadWorkflow: (wf) => {
    const nodes: Node[] = (wf.definition?.nodes || []).map((n: any) => ({
      id: n.id,
      type: n.type,
      position: n.position,
      data: n.data || {},
    }))
    const edges: Edge[] = (wf.definition?.edges || []).map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle,
      targetHandle: e.targetHandle,
      animated: true,
    }))
    set({
      nodes,
      edges,
      meta: {
        id: wf.id,
        name: wf.name,
        description: wf.description || "",
        version: wf.version || 1,
        isSaved: true,
        isDirty: false,
      },
      run: { ...defaultRun },
      selectedNodeId: null,
    })
  },

  markDirty: () =>
    set((s) => ({ meta: { ...s.meta, isDirty: true } })),

  setRunState: (run) => set((s) => ({ run: { ...s.run, ...run } })),

  updateNodeRunState: (nodeId, state) =>
    set((s) => ({
      run: {
        ...s.run,
        nodeStates: { ...s.run.nodeStates, [nodeId]: state },
      },
    })),

  pushHistoryEvent: (event) =>
    set((s) => {
      const history = [...s.run.history, event]
      return { run: { ...s.run, history } }
    }),

  setScrubIndex: (index) =>
    set((s) => {
      if (index === null) {
        return { run: { ...s.run, scrubIndex: null, scrubbedNodeStates: {} } }
      }
      
      const scrubbedNodeStates: Record<string, any> = {}
      
      // Replay history up to index
      for (let i = 0; i <= index && i < s.run.history.length; i++) {
        const ev = s.run.history[i]
        if (ev.type === 'node_start') {
          scrubbedNodeStates[ev.nodeId] = { status: 'running' }
        } else if (ev.type === 'node_complete') {
          scrubbedNodeStates[ev.nodeId] = { status: 'completed', output: ev.output, duration_s: ev.duration_s }
        } else if (ev.type === 'node_error') {
          scrubbedNodeStates[ev.nodeId] = { status: 'failed', error: ev.error }
        }
      }

      return { run: { ...s.run, scrubIndex: index, scrubbedNodeStates } }
    }),

  appendLog: (line) =>
    set((s) => ({
      run: { ...s.run, logs: [...s.run.logs, line] },
    })),

  resetRun: () => set({ run: { ...defaultRun } }),
}))
