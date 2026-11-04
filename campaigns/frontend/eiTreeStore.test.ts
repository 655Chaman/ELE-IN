import { describe, it, expect } from "bun:test"
import { hasDagCycles, dagToTree } from "./eiTreeStore"

describe("Phase D: DAG Sequence Engine & Cycle Pre-Flight (hasDagCycles & dagToTree)", () => {
  it("Layer 2 (Paranoia): hasDagCycles immediately flags single-node self-loops", () => {
    const nodes = [{ id: "step_1", type: "connection_request" }]
    const edges = [{ source: "step_1", target: "step_1" }]
    expect(hasDagCycles(nodes, edges)).toBe(true)
  })

  it("Layer 0 (Foundational): hasDagCycles flags simple 2-node cycles", () => {
    const nodes = [
      { id: "node_a", type: "connection_request" },
      { id: "node_b", type: "send_message" },
    ]
    const edges = [
      { source: "node_a", target: "node_b" },
      { source: "node_b", target: "node_a" },
    ]
    expect(hasDagCycles(nodes, edges)).toBe(true)
  })

  it("Layer 1 (Environmental): hasDagCycles handles dual edge keys (source_node_id / target_node_id)", () => {
    const nodes = [
      { id: "start", type: "sequence_start" },
      { id: "step1", type: "connection_request" },
      { id: "step2", type: "send_message" },
    ]
    const edges = [
      { source_node_id: "start", target_node_id: "step1" },
      { source_node_id: "step1", target_node_id: "step2" },
    ]
    expect(hasDagCycles(nodes, edges)).toBe(false)
  })

  it("Layer 1 (Environmental): hasDagCycles ignores dangling edges to deleted nodes without crashing", () => {
    const nodes = [
      { id: "root", type: "sequence_start" },
      { id: "valid_child", type: "send_email" },
    ]
    const edges = [
      { source: "root", target: "valid_child" },
      { source: "valid_child", target: "non_existent_node_999" },
    ]
    expect(hasDagCycles(nodes, edges)).toBe(false)
  })

  it("Layer 0 & 1: dagToTree accurately reconstructs multi-channel fallback sequences", () => {
    const nodes = [
      { id: "n1", type: "connection_request", data: { label: "Connect" } },
      { id: "n2", type: "if_connected", data: { label: "Check Connected" } },
      { id: "n3", type: "send_message", data: { body: "Hey there" } },
      { id: "n4", type: "send_inmail", data: { subject: "Sub", body: "Body" } },
    ]
    const edges = [
      { source: "n1", target: "n2" },
      { source: "n2", target: "n3", sourceHandle: "connected" },
      { source: "n2", target: "n4", sourceHandle: "not_connected" },
    ]

    const tree = dagToTree(nodes, edges)
    expect(tree.length).toBe(1)
    expect(tree[0].id).toBe("n1")
    
    // Connected children under the primary branch (Accepted)
    const n2Node = tree[0].children?.Accepted?.[0] || tree[0].children?.output?.[0] || tree[0].children?.then?.[0]
    expect(n2Node).toBeDefined()
    expect(n2Node?.id).toBe("n2")
  })
})
