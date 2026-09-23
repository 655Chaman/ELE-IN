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

export const HR_TEMPLATES: EITemplate[] = [
  {
    "id": "get_customers",
    "name": "Get Customers",
    "description": "Message people who can buy. Goal: book a meeting.",
    "connectionRate": 42,
    "replyRate": 18,
    "uses": 1240,
    "difficulty": "beginner",
    "tags": [
      "cold-outreach"
    ],
    "nodes": [
      {
        "id": "gc_1",
        "type": "connection_request",
        "position": {
          "x": 250,
          "y": 100
        },
        "data": {
          "note_strategy": "Fixed note",
          "note": "Hi {{first_name}}, saw what you're doing at {{company}} and would love to connect.",
          "delayDays": 0
        }
      },
      {
        "id": "gc_2",
        "type": "send_message",
        "position": {
          "x": 250,
          "y": 300
        },
        "data": {
          "body": "Thanks for connecting, {{first_name}}. We're helping companies similar to {{company}} scale their pipeline. Would you be open to a quick chat this week?",
          "delayDays": 0
        }
      },
      {
        "id": "gc_3",
        "type": "send_message",
        "position": {
          "x": 250,
          "y": 500
        },
        "data": {
          "body": "Just bubbling this up, {{first_name}}. Let me know if you have 10 mins next week.",
          "delayDays": 3
        }
      }
    ],
    "edges": [
      {
        "id": "e_gc_1_2",
        "source": "gc_1",
        "target": "gc_2",
        "sourceHandle": "Accepted"
      },
      {
        "id": "e_gc_2_3",
        "source": "gc_2",
        "target": "gc_3",
        "sourceHandle": "Not Replied Yet"
      }
    ]
  },
  {
    "id": "hire_people",
    "name": "Hire People",
    "description": "Message people you want on the team. Goal: a hire.",
    "connectionRate": 55,
    "replyRate": 25,
    "uses": 890,
    "difficulty": "beginner",
    "tags": [
      "recruiting"
    ],
    "nodes": [
      {
        "id": "hp_1",
        "type": "connection_request",
        "position": {
          "x": 250,
          "y": 100
        },
        "data": {
          "note_strategy": "Fixed note",
          "note": "Hi {{first_name}}, really impressed by your background. Would love to connect.",
          "delayDays": 0
        }
      },
      {
        "id": "hp_2",
        "type": "send_message",
        "position": {
          "x": 250,
          "y": 300
        },
        "data": {
          "body": "Thanks for connecting! We're currently expanding our team at Ele-in and your experience caught my eye. Open to a quick chat about what we're building?",
          "delayDays": 0
        }
      },
      {
        "id": "hp_3",
        "type": "send_message",
        "position": {
          "x": 250,
          "y": 500
        },
        "data": {
          "body": "I know you're probably busy, {{first_name}}, but wanted to follow up. Let me know if you'd be open to a quick intro call.",
          "delayDays": 3
        }
      }
    ],
    "edges": [
      {
        "id": "e_hp_1_2",
        "source": "hp_1",
        "target": "hp_2",
        "sourceHandle": "Accepted"
      },
      {
        "id": "e_hp_2_3",
        "source": "hp_2",
        "target": "hp_3",
        "sourceHandle": "Not Replied Yet"
      }
    ]
  },
  {
    "id": "get_intros",
    "name": "Get Intros",
    "description": "Message people who can open a door — investor, partner, or their network.",
    "connectionRate": 35,
    "replyRate": 12,
    "uses": 450,
    "difficulty": "beginner",
    "tags": [
      "partnerships"
    ],
    "nodes": [
      {
        "id": "gi_1",
        "type": "connection_request",
        "position": {
          "x": 250,
          "y": 100
        },
        "data": {
          "note_strategy": "Fixed note",
          "note": "Hi {{first_name}}, building my network in the space and would love to connect.",
          "delayDays": 0
        }
      },
      {
        "id": "gi_2",
        "type": "send_message",
        "position": {
          "x": 250,
          "y": 300
        },
        "data": {
          "body": "Thanks for the connection, {{first_name}}. I'm currently exploring some strategic partnerships and would love to get your thoughts, or an intro to someone in your network who might be a fit.",
          "delayDays": 0
        }
      },
      {
        "id": "gi_3",
        "type": "send_message",
        "position": {
          "x": 250,
          "y": 500
        },
        "data": {
          "body": "Just following up here, {{first_name}}. No worries if you're swamped right now, but would appreciate any pointers!",
          "delayDays": 3
        }
      }
    ],
    "edges": [
      {
        "id": "e_gi_1_2",
        "source": "gi_1",
        "target": "gi_2",
        "sourceHandle": "Accepted"
      },
      {
        "id": "e_gi_2_3",
        "source": "gi_2",
        "target": "gi_3",
        "sourceHandle": "Not Replied Yet"
      }
    ]
  }
];
