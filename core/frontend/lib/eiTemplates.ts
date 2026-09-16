import type { Node, Edge } from "@xyflow/react"
export const TEMPLATE_TAGS = ["all", "cold-outreach", "recruiting", "agency", "partnerships", "re-engagement", "thought-leadership", "custom"]
export const TEMPLATE_TAG_LABELS: Record<string, string> = {
  all: "All",
  "cold-outreach": "Cold outreach",
  recruiting: "Recruiting",
  agency: "Agency",
  partnerships: "BD / Partnerships",
  "re-engagement": "Re-engagement",
  "thought-leadership": "Brand building",
  custom: "Your Templates",
}
export interface StickyNote {
  title: string
  body: string
  why: string
}
export interface EITemplate {
  id: string
  name: string
  description: string
  connectionRate: number
  replyRate: number
  uses: number
  difficulty: "beginner" | "intermediate" | "advanced"
  tags: string[]
  bestFor?: string
  nodes: Node[]
  edges: Edge[]
  stickyNotes?: Record<string, StickyNote>
}
const edgeStyle = { stroke: "#6366f1", strokeWidth: 2 }
const edgeLabelStyle = { fill: "#a1a1aa", fontSize: 10 }
const edgeLabelBg = { fill: "#18181b" }
const edgeGreen = { stroke: "#10b981", strokeWidth: 2 }
const edgeRed = { stroke: "#f43f5e", strokeWidth: 2 }
export const HR_TEMPLATES: EITemplate[] = [];
