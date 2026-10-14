import type { EINode, EIEdge } from "./eiTypes"


export const TEMPLATE_TAGS = ["all", "blue-ocean", "cold-outreach", "recruiting", "agency", "partnerships", "re-engagement", "thought-leadership", "custom"]
export const TEMPLATE_TAG_LABELS: Record<string, string> = {
  all: "All",
  "blue-ocean": "Blue Ocean Moats",
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
  nodes: EINode[]
  edges: EIEdge[]
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
          "note": "Hi {{first_name|there}}, saw what you're doing at {{company|your company}} and would love to connect.",
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
          "body": "Thanks for connecting, {{first_name|there}}. We're helping companies similar to {{company|yours}} scale their pipeline. Would you be open to a quick chat this week?",
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
          "body": "Just bubbling this up, {{first_name|there}}. Let me know if you have 10 mins next week.",
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
        "sourceHandle": "then"
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
          "note": "Hi {{first_name|there}}, really impressed by your background. Would love to connect.",
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
          "body": "I know you're probably busy, {{first_name|there}}, but wanted to follow up. Let me know if you'd be open to a quick intro call.",
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
        "sourceHandle": "then"
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
          "note": "Hi {{first_name|there}}, building my network in the space and would love to connect.",
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
          "body": "Thanks for the connection, {{first_name|there}}. I'm currently exploring some strategic partnerships and would love to get your thoughts, or an intro to someone in your network who might be a fit.",
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
          "body": "Just following up here, {{first_name|there}}. No worries if you're swamped right now, but would appreciate any pointers!",
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
        "sourceHandle": "then"
      }
    ]
  },
  {
    "id": "social_warmer_inbound",
    "name": "Social Warmer (Inbound Nurture)",
    "description": "Auto-warm prospects prior to outreach: View Profile -> Like Post -> Comment -> Connect -> Warm Intro. Boosts acceptance rate to 68%+.",
    "connectionRate": 68,
    "replyRate": 31,
    "uses": 3420,
    "difficulty": "intermediate",
    "tags": ["blue-ocean", "cold-outreach", "thought-leadership"],
    "nodes": [
      {
        "id": "sw_1",
        "type": "view_profile",
        "position": { "x": 250, "y": 100 },
        "data": { "delayDays": 0, "label": "View Profile" }
      },
      {
        "id": "sw_2",
        "type": "like_post",
        "position": { "x": 250, "y": 250 },
        "data": { "delayDays": 1, "label": "Like Recent Post" }
      },
      {
        "id": "sw_3",
        "type": "comment_on_post",
        "position": { "x": 250, "y": 400 },
        "data": { "delayDays": 1, "label": "Leave Comment" }
      },
      {
        "id": "sw_4",
        "type": "connection_request",
        "position": { "x": 250, "y": 550 },
        "data": {
          "delayDays": 1,
          "label": "Connection Request",
          "note_strategy": "Blank",
          "note": ""
        }
      },
      {
        "id": "sw_5",
        "type": "if_connected",
        "position": { "x": 250, "y": 700 },
        "data": { "delayDays": 3, "label": "If Connected?" }
      },
      {
        "id": "sw_6",
        "type": "send_message",
        "position": { "x": 250, "y": 850 },
        "data": {
          "delayDays": 0,
          "label": "Send Message",
          "body": "Hey {{first_name|there}}, loved your recent posts. Great connecting with you!"
        }
      }
    ],
    "edges": [
      { "id": "e_sw_1_2", "source": "sw_1", "target": "sw_2", "sourceHandle": "then" },
      { "id": "e_sw_2_3", "source": "sw_2", "target": "sw_3", "sourceHandle": "then" },
      { "id": "e_sw_3_4", "source": "sw_3", "target": "sw_4", "sourceHandle": "then" },
      { "id": "e_sw_4_5", "source": "sw_4", "target": "sw_5", "sourceHandle": "then" },
      { "id": "e_sw_5_6", "source": "sw_5", "target": "sw_6", "sourceHandle": "Connected" }
    ]
  },
  {
    "id": "omnichannel_waterfall",
    "name": "Omnichannel Waterfall (Zero-Cost Discovery)",
    "description": "Connect on LinkedIn. If pending after 5 days, automatically resolves verified corporate email via Zero-Cost SMTP Discovery and delivers an email touchpoint.",
    "connectionRate": 48,
    "replyRate": 38,
    "uses": 4810,
    "difficulty": "advanced",
    "tags": ["blue-ocean", "cold-outreach", "agency"],
    "nodes": [
      {
        "id": "ow_1",
        "type": "connection_request",
        "position": { "x": 250, "y": 100 },
        "data": {
          "delayDays": 0,
          "label": "Connection Request",
          "note_strategy": "Fixed note",
          "note": "Hi {{first_name|there}}, saw your work at {{company|your company}} and wanted to connect."
        }
      },
      {
        "id": "ow_2",
        "type": "seamless_identity_matching",
        "position": { "x": 250, "y": 300 },
        "data": {
          "delayDays": 5,
          "label": "Seamless Identity Match",
          "timeout_days": 5,
          "auto_discover_email": true
        }
      },
      {
        "id": "ow_3",
        "type": "send_message",
        "position": { "x": 150, "y": 500 },
        "data": {
          "delayDays": 0,
          "label": "Send Message",
          "body": "Thanks for connecting, {{first_name|there}}! Would love to hear how your team is tackling growth this quarter."
        }
      },
      {
        "id": "ow_4",
        "type": "send_email",
        "position": { "x": 350, "y": 500 },
        "data": {
          "delayDays": 0,
          "label": "Send Work Email",
          "subject": "Connecting regarding {{company|your team}}",
          "body": "Hi {{first_name|there}},\n\nI sent you a note on LinkedIn earlier this week, but wanted to drop a quick line here in case you're swamped.\n\nOpen to a brief chat?"
        }
      }
    ],
    "edges": [
      { "id": "e_ow_1_2", "source": "ow_1", "target": "ow_2", "sourceHandle": "then" },
      { "id": "e_ow_2_3", "source": "ow_2", "target": "ow_3", "sourceHandle": "Connected" },
      { "id": "e_ow_2_4", "source": "ow_2", "target": "ow_4", "sourceHandle": "Email Discovered" }
    ]
  },
  {
    "id": "bayesian_account_nurture",
    "name": "Bayesian ICP Account-Based Penetration",
    "description": "AI qualifies leads via Thompson Sampling prior to engagement, personalizes opening hooks, and routes responses dynamically based on connection status.",
    "connectionRate": 58,
    "replyRate": 29,
    "uses": 2150,
    "difficulty": "advanced",
    "tags": ["blue-ocean", "cold-outreach", "partnerships"],
    "nodes": [
      {
        "id": "bn_1",
        "type": "icp_score_gate",
        "position": { "x": 250, "y": 100 },
        "data": {
          "delayDays": 0,
          "label": "ICP Score Gate",
          "score_threshold": 70
        }
      },
      {
        "id": "bn_2",
        "type": "ai_personalize",
        "position": { "x": 250, "y": 250 },
        "data": {
          "delayDays": 0,
          "label": "AI Personalize",
          "custom_rules": "Focus on relevance and brevity."
        }
      },
      {
        "id": "bn_3",
        "type": "connection_request",
        "position": { "x": 250, "y": 400 },
        "data": {
          "delayDays": 0,
          "label": "Connection Request",
          "note_strategy": "AI Personalized Note"
        }
      },
      {
        "id": "bn_4",
        "type": "if_connected",
        "position": { "x": 250, "y": 550 },
        "data": { "delayDays": 3, "label": "If Connected?" }
      },
      {
        "id": "bn_5",
        "type": "send_message",
        "position": { "x": 150, "y": 700 },
        "data": {
          "delayDays": 0,
          "label": "Send Message",
          "body": "Hi {{first_name|there}}, thanks for connecting. Would you be open to exchanging notes on {{company|your company}}'s initiatives?"
        }
      },
      {
        "id": "bn_6",
        "type": "zero_cost_discovery",
        "position": { "x": 350, "y": 700 },
        "data": {
          "delayDays": 0,
          "label": "Zero-Cost Email Discovery",
          "verify_mx": true
        }
      },
      {
        "id": "bn_7",
        "type": "send_email",
        "position": { "x": 350, "y": 850 },
        "data": {
          "delayDays": 1,
          "label": "Send Work Email",
          "subject": "Quick note for {{first_name|there}}",
          "body": "Hi {{first_name|there}},\n\nWanted to reach out directly regarding your team at {{company|your company}}."
        }
      }
    ],
    "edges": [
      { "id": "e_bn_1_2", "source": "bn_1", "target": "bn_2", "sourceHandle": "Strong fit (>75)" },
      { "id": "e_bn_2_3", "source": "bn_2", "target": "bn_3", "sourceHandle": "then" },
      { "id": "e_bn_3_4", "source": "bn_3", "target": "bn_4", "sourceHandle": "then" },
      { "id": "e_bn_4_5", "source": "bn_4", "target": "bn_5", "sourceHandle": "Connected" },
      { "id": "e_bn_4_6", "source": "bn_4", "target": "bn_6", "sourceHandle": "Not connected" },
      { "id": "e_bn_6_7", "source": "bn_6", "target": "bn_7", "sourceHandle": "Found" }
    ]
  },
  {
    "id": "inbound_ghostwriter_omnichannel",
    "name": "Inbound Ghostwriter & Omnichannel Fallback",
    "description": "AI ghostwrites an authentic comment on the lead's latest post and likes it, sends a high-converting blank invite, waits for a reply with RAG objection handling, and triggers a seamless email fallback if unaccepted.",
    "connectionRate": 74,
    "replyRate": 44,
    "uses": 5120,
    "difficulty": "advanced",
    "tags": ["blue-ocean", "cold-outreach", "thought-leadership"],
    "nodes": [
      {
        "id": "ig_1",
        "type": "inbound_ghostwriting",
        "position": { "x": 250, "y": 100 },
        "data": {
          "delayDays": 0,
          "label": "AI Inbound Ghostwriter",
          "comment_mode": "AI-generated (from post content)",
          "like_post": true
        }
      },
      {
        "id": "ig_2",
        "type": "connection_no_note",
        "position": { "x": 250, "y": 250 },
        "data": {
          "delayDays": 1,
          "label": "Blank Connection Request",
          "withdraw_enabled": true,
          "withdraw_days": 14
        }
      },
      {
        "id": "ig_3",
        "type": "wait_for_reply",
        "position": { "x": 250, "y": 400 },
        "data": {
          "delayDays": 3,
          "label": "Wait for Reply",
          "wait_days": 3
        }
      },
      {
        "id": "ig_4",
        "type": "ai_generate_reply",
        "position": { "x": 100, "y": 550 },
        "data": {
          "delayDays": 0,
          "label": "AI Knowledge Base Reply"
        }
      },
      {
        "id": "ig_5",
        "type": "mark_interested",
        "position": { "x": 100, "y": 700 },
        "data": {
          "delayDays": 0,
          "label": "Mark as Interested"
        }
      },
      {
        "id": "ig_6",
        "type": "seamless_identity_matching",
        "position": { "x": 400, "y": 550 },
        "data": {
          "delayDays": 4,
          "label": "Seamless Identity Match",
          "timeout_days": 7,
          "auto_discover_email": true
        }
      },
      {
        "id": "ig_7",
        "type": "send_message",
        "position": { "x": 300, "y": 700 },
        "data": {
          "delayDays": 1,
          "label": "Send Personalized DM",
          "body": "Hey {{first_name|there}}, loved your recent thoughts on LinkedIn! Wanted to connect and see what you're focusing on at {{company|your company}} this quarter."
        }
      },
      {
        "id": "ig_8",
        "type": "send_email",
        "position": { "x": 500, "y": 700 },
        "data": {
          "delayDays": 1,
          "label": "Multichannel Email Fallback",
          "subject": "Connecting after your recent LinkedIn post ({{first_name|there}})",
          "body": "Hi {{first_name|there}},\n\nI commented on your recent LinkedIn post earlier this week and sent a connection invite.\n\nReaching out directly here in case you're not on LinkedIn often — would love to connect regarding {{company|your company}}."
        }
      }
    ],
    "edges": [
      { "id": "e_ig_1_2", "source": "ig_1", "target": "ig_2", "sourceHandle": "then" },
      { "id": "e_ig_2_3", "source": "ig_2", "target": "ig_3", "sourceHandle": "Accepted" },
      { "id": "e_ig_3_4", "source": "ig_3", "target": "ig_4", "sourceHandle": "Replied" },
      { "id": "e_ig_4_5", "source": "ig_4", "target": "ig_5", "sourceHandle": "then" },
      { "id": "e_ig_3_6", "source": "ig_3", "target": "ig_6", "sourceHandle": "Timeout" },
      { "id": "e_ig_6_7", "source": "ig_6", "target": "ig_7", "sourceHandle": "Connected" },
      { "id": "e_ig_6_8", "source": "ig_6", "target": "ig_8", "sourceHandle": "Email Discovered" }
    ]
  }
];
