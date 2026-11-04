import { describe, it, expect } from "bun:test"
import {
  normalizeToBlueprint,
  validateBlueprint,
  exportBlueprint,
  repairTruncatedJson,
  parseBlueprintJsonString,
  sanitizeHexColor,
  applyVariableFallbacksToTree,
} from "../../core/frontend/lib/blueprintSchema"
import { dagToTree, treeToDag } from "./eiTreeStore"

describe("Blueprint Import & Export Paranoia Architecture", () => {
  // ─── Layer 0: Foundational Mechanization ───────────────────────────────────
  describe("Layer 0: Foundational Functionality", () => {
    it("exports a standard tree to a valid elein-blueprint-v1 payload", () => {
      const mockTree: any[] = [
        {
          id: "node-1",
          type: "visit_profile",
          data: { label: "Profile Visit", delay: 1 },
          children: {
            then: [
              {
                id: "node-2",
                type: "connection_request",
                data: { message: "Hello {{first_name}}", delay: 2 },
                children: {},
              },
            ],
          },
        },
      ]

      const exported = exportBlueprint(mockTree, [], {
        name: "Test Sequence",
        description: "A test blueprint",
      })

      expect(exported.schema).toBe("elein-blueprint-v1")
      expect(exported.metadata.name).toBe("Test Sequence")
      expect(exported.sequence.rootNodes.length).toBe(1)
      expect(exported.metadata.stats?.nodeCount).toBe(2)

      const validation = validateBlueprint(exported)
      expect(validation.isValid).toBe(true)
      expect(validation.errors.length).toBe(0)
    })
  })

  // ─── Layer 1: Environmental Failure Analysis ──────────────────────────────
  describe("Layer 1: Environmental Failure Analysis & Format Ingestion", () => {
    it("normalizes and validates a legacy DAG payload with nodes and edges", () => {
      const legacyDag = {
        name: "Legacy Outreach",
        nodes: [
          { id: "1", type: "visit_profile", data: { label: "Step 1" } },
          { id: "2", type: "send_message", data: { message: "Hi!" } },
        ],
        edges: [
          { id: "e1-2", source: "1", target: "2", sourceHandle: "then" },
        ],
      }

      const normalized = normalizeToBlueprint(legacyDag)
      expect(normalized).not.toBeNull()
      expect(normalized?.schema).toBe("elein-blueprint-v1")
      expect(normalized?.sequence?.rootNodes?.length).toBe(1)

      const validation = validateBlueprint(legacyDag)
      expect(validation.isValid).toBe(true)
      expect(validation.parsedBlueprint?.sequence.rootNodes[0].id).toBe("1")
    })

    it("normalizes and validates a raw rootNodes array", () => {
      const rawPayload = {
        rootNodes: [
          {
            id: "step-a",
            type: "invite_to_connect",
            data: {},
            children: {},
          },
        ],
      }

      const validation = validateBlueprint(rawPayload)
      expect(validation.isValid).toBe(true)
      expect(validation.parsedBlueprint?.sequence.rootNodes.length).toBe(1)
    })

    it("normalizes and validates a bare node tree array", () => {
      const bareArray = [
        {
          id: "step-100",
          type: "like_recent_post",
          data: {},
          children: {},
        },
      ]

      const validation = validateBlueprint(bareArray)
      expect(validation.isValid).toBe(true)
      expect(validation.parsedBlueprint?.metadata.name).toBe("Imported Sequence")
      expect(validation.parsedBlueprint?.sequence.rootNodes.length).toBe(1)
    })

    it("resists cyclic graphs without hanging or causing recursion stack overflow", () => {
      // Create circular reference
      const cyclicalTree: any = {
        id: "cyclic-root",
        type: "visit_profile",
        data: {},
        children: {
          then: [],
        },
      }
      const childNode: any = {
        id: "cyclic-child",
        type: "send_message",
        data: {},
        children: {
          then: [cyclicalTree], // Cycle pointing back to root
        },
      }
      cyclicalTree.children.then.push(childNode)

      const exported = exportBlueprint([cyclicalTree], [])
      expect(exported.schema).toBe("elein-blueprint-v1")
      // Cycles must be broken with sequence_end or cycle markers
      expect(exported.sequence.rootNodes.length).toBe(1)
    })

    it("safely handles null, undefined, and malformed inputs to dagToTree and treeToDag", () => {
      expect(dagToTree(null as any, null as any)).toEqual([])
      expect(dagToTree(undefined as any, undefined as any)).toEqual([])
      expect(dagToTree([{ invalid: true }] as any, [])).toEqual([])

      expect(treeToDag(null as any)).toEqual({ nodes: [], edges: [] })
      expect(treeToDag(undefined as any)).toEqual({ nodes: [], edges: [] })
      expect(treeToDag([null, undefined, {}] as any)).toEqual({ nodes: [], edges: [] })
    })
  })

  // ─── Layer 2: Human Paranoia ──────────────────────────────────────────────
  describe("Layer 2: Human Paranoia & Truncated Recovery", () => {
    it("safely repairs partially truncated JSON strings", () => {
      const truncated = '{"schema":"elein-blueprint-v1","metadata":{"name":"Incomplete'
      const repaired = repairTruncatedJson(truncated)
      expect(() => JSON.parse(repaired)).not.toThrow()
    })

    it("detects and auto-repairs truncated JSON payloads in parseBlueprintJsonString", () => {
      const truncated = '{"schema":"elein-blueprint-v1","metadata":{"name":"Auto Healed Test","version":"1.0.0"},"sequence":{"rootNodes":[]'
      const parsed = parseBlueprintJsonString(truncated)
      expect(parsed.metadata.name).toBe("Auto Healed Test")
      expect(parsed._wasAutoRepaired).toBe(true)
    })

    it("safely handles empty strings and invalid types in validateBlueprint", () => {
      expect(validateBlueprint("").isValid).toBe(false)
      expect(validateBlueprint(null).isValid).toBe(false)
      expect(validateBlueprint(12345).isValid).toBe(false)
      expect(validateBlueprint({}).isValid).toBe(false)
    })

    it("sanitizes CSV / formula injection prefixes across node strings and notes", () => {
      const maliciousTree: any[] = [
        {
          id: "node-x",
          type: "send_message",
          data: {
            message: "=cmd|' /C calc'!A0",
            label: "+SUM(1+1)",
            note: "@evil_macro",
          },
          children: {},
        },
      ]

      const exported = exportBlueprint(maliciousTree, [], {
        name: "=HYPERLINK('http://evil.com')",
      })

      const exportedNode = exported.sequence.rootNodes[0]
      expect(exportedNode.data.message.startsWith("'=")).toBe(true)
      expect(exportedNode.data.label.startsWith("'+")).toBe(true)
      expect(exportedNode.data.note.startsWith("'@")).toBe(true)
      expect(exported.metadata.name.startsWith("'=")).toBe(true)
    })

    it("sanitizes brand accent colors to prevent CSS injection", () => {
      expect(sanitizeHexColor("#6366f1")).toBe("#6366f1")
      expect(sanitizeHexColor("#fff")).toBe("#fff")
      expect(sanitizeHexColor("javascript:alert(1)")).toBe("#6366f1")
      expect(sanitizeHexColor("red; background-image: url(...)")).toBe("#6366f1")
      expect(sanitizeHexColor(undefined)).toBe("#6366f1")
    })

    it("rejects blueprint JSON strings exceeding the 500KB safety ceiling", () => {
      const hugeString = "a".repeat(500001)
      expect(() => parseBlueprintJsonString(hugeString)).toThrow(/500KB/)
    })

    it("resists infinite recursion in variable fallbacks when given circular graphs", () => {
      const cyclicNode: any = {
        id: "cyclic-1",
        type: "send_message",
        data: { message: "Hello {{first_name}}" },
        children: {},
      }
      cyclicNode.children.then = [cyclicNode] // Direct self-cycle

      expect(() => {
        applyVariableFallbacksToTree([cyclicNode], { first_name: "there" })
      }).not.toThrow()
    })
  })
})
