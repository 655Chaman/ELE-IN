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
    "name": "Enterprise Outbound & Value Diagnostic",
    "description": "Engage revenue and operations executives with high-signal consultative benchmark telemetry. Goal: Qualified discovery pipeline.",
    "connectionRate": 48,
    "replyRate": 24,
    "uses": 2480,
    "difficulty": "intermediate",
    "tags": [
      "cold-outreach",
      "agency"
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
          "note": "{Hi|Hello} {{first_name|there}}, {tracked your architecture milestones at|following your operational expansion at} {{company|your team}}. {Would value connecting to exchange notes on high-scale outbound telemetry.|Thought it prudent to share our benchmarking data with your team.}",
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
          "body": "{Great to connect|Appreciate the connection}, {{first_name|there}}.\n\n{We recently benchmarked pipeline acceleration across Tier-1 enterprise SaaS orgs.|Our engineering team analyzed deliverability drift and pipeline leakage across 40+ enterprise teams.}\n\n{One key finding was that multi-channel identity matching reduced acquisition cost by 43% without domain burning.|The data showed automated cadence jitter protects sender reputation while increasing qualified reply velocity.}\n\n{Open to a brief 4-minute diagnostic review, or should I forward our whitepaper first?|Would you prefer a short summary deck, or a quick 5-minute technical briefing?}",
          "delayDays": 1
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
          "body": "{Brief follow-up|Quick touchpoint}, {{first_name|there}} — {understand your quarter is packed with strategic priorities|no presumption that this is top of inbox right now}.\n\n{If your team is already hitting 98%+ primary inbox placement and target pipeline, feel free to archive this.|If you'd like our Q3 deliverability & pipeline diagnostic rubric for your team to review independently, let me know and I'll send it over.}",
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
    "name": "Executive & Leadership Talent Sourcing",
    "description": "Discreet, high-touch headhunting for key individual contributors and VP-level executives. Goal: Talent acquisition pipeline.",
    "connectionRate": 62,
    "replyRate": 32,
    "uses": 1420,
    "difficulty": "intermediate",
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
          "note": "{Hi|Hello} {{first_name|there}}, {tracking your exceptional technical execution at|admiring the high-performance culture your team is building at} {{company|your company}}. {Would welcome connecting to follow your trajectory.|Would value staying connected as our paths cross in the industry.}",
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
          "body": "{Thanks for connecting|Great to connect}, {{first_name|there}}.\n\n{Our leadership team is discreetly assembling a Tier-1 executive pod to architect our next phase of scale.|We are currently expanding our core engineering and product leadership for a high-conviction growth initiative.}\n\n{Given your track record of scaling mission-critical systems at|Having followed your technical milestones at} {{company|your organization}}, {your background stood out immediately to our founders.|we believe your domain expertise aligns directly with the architectural challenges we are solving.}\n\n{Would you be open to an informal, confidential 10-minute coffee chat with our VP of Engineering? Zero pressure either way.|Would you have 10 minutes next Tuesday for a high-level, confidential exchange with our founding team?}",
          "delayDays": 1
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
          "body": "{Completely understand if you are deeply invested in your current mission at|Respecting your current focus and priorities at} {{company|your team}}, {{first_name|there}}.\n\n{Happy to stay connected in the background and cheer on your continued wins.|If timing aligns better down the road, my door is always open. Wishing you and your team continued momentum!}",
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
    "name": "Executive & Advisory Network Syndication",
    "description": "Peer-to-peer executive dialogue with founders, institutional investors, and strategic alliance leaders. Goal: High-leverage partnerships.",
    "connectionRate": 44,
    "replyRate": 21,
    "uses": 980,
    "difficulty": "intermediate",
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
          "note": "{Hi|Hello} {{first_name|there}}, {following your strategic market thesis and product expansion at|admiring your venture leadership at} {{company|your team}}. {Would value connecting to exchange executive perspectives.|Would appreciate the opportunity to stay connected as strategic peers.}",
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
          "body": "{Appreciate the connection|Great to connect}, {{first_name|there}}.\n\n{We are currently evaluating strategic integration ecosystems and institutional distribution partnerships in your space.|Our team is finalizing our enterprise integration roadmap and syndicating strategic alliances with leading platforms.}\n\n{Given your vantage point at {{company|your company}}, we would greatly value your perspective on enterprise workflow consolidation.|Would love to get 7 minutes of your perspective on enterprise integration vectors, or a quick introduction to your Head of Strategic Alliances.}\n\n{Would you be open to a brief peer-level exchange next week?|Are you open to a high-level briefing on how we could drive mutual client retention?}",
          "delayDays": 1
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
          "body": "{Brief follow-up|Quick note}, {{first_name|there}} — {recognize your calendar is booked with tier-1 initiatives|no worries if your bandwidth is directed toward current quarterly goals}.\n\n{Happy to reconnect when strategic planning begins for next half.|If there is an alliance or partner lead on your team who owns this vector, feel free to introduce us directly. Appreciate your time!}",
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
    "name": "Social Warmer & Brand Inbound Nurture",
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
          "body": "{Great to connect|Appreciate the connection}, {{first_name|there}}!\n\n{Your recent post regarding industry dynamics resonated strongly with our team.|Really enjoyed your perspective on scaling operations in your recent update.}\n\n{We are noticing similar patterns across enterprise engineering teams tackling distributed workflow orchestration.|Particularly agreed with your point on prioritizing high-signal execution over brute-force automation.}\n\n{Looking forward to following your future updates and exchanging notes on modern infrastructure!|Would love to stay closely connected as our industry navigates these shifts.}"
        }
      }
    ],
    "edges": [
      { "id": "e_sw_1_2", "source": "sw_1", "target": "sw_2", "sourceHandle": "then" },
      { "id": "e_sw_2_3", "source": "sw_2", "target": "sw_3", "sourceHandle": "then" },
      { "id": "e_sw_3_4", "source": "sw_3", "target": "sw_4", "sourceHandle": "then" },
      { "id": "e_sw_4_5", "source": "sw_4", "target": "sw_5", "sourceHandle": "Accepted" },
      { "id": "e_sw_5_6", "source": "sw_5", "target": "sw_6", "sourceHandle": "Connected" }
    ]
  },
  {
    "id": "omnichannel_waterfall",
    "name": "Omnichannel Waterfall (Zero-Cost Discovery & Fallback)",
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
          "note": "{Hi|Hello} {{first_name|there}}, {noticed your team's engineering velocity at|following your leadership at} {{company|your company}}. {Would value connecting to share our latest enterprise benchmark findings.|Would love to stay in touch as peers in the revenue operations ecosystem.}"
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
          "body": "{Thanks for connecting|Great to connect}, {{first_name|there}}!\n\n{Curious how your leadership team is navigating pipeline efficiency and outbound deliverability this quarter at|Wanted to ask how your team is approaching account-based orchestration this year at} {{company|your company}}.\n\n{We recently released an enterprise playbook on preventing domain burnout while 3x-ing target engagement. Happy to share the raw benchmark if useful!|We put together an architectural comparison on multi-channel waterfall routing for engineering leaders. Would you be open to a 2-minute overview?}"
        }
      },
      {
        "id": "ow_4",
        "type": "send_email",
        "position": { "x": 350, "y": 500 },
        "data": {
          "delayDays": 0,
          "label": "Send Work Email",
          "subject": "{Quick question regarding|Connecting on} {{company|your team}}'s outbound architecture",
          "body": "Hi {{first_name|there}},\n\nI sent you a brief note on LinkedIn earlier this week regarding {{company|your company}}'s operational milestones, but wanted to drop a concise note here in case your LinkedIn inbox is overwhelmed.\n\nWe recently mapped out how Tier-1 B2B teams are decoupling sender identities using residential proxy pools and envelope encryption to maintain 99%+ deliverability.\n\nWould you be open to reviewing the 3-page executive summary, or should I reconnect with your VP of Operations directly?\n\nBest regards,\n[Your Name]"
        }
      }
    ],
    "edges": [
      { "id": "e_ow_1_2", "source": "ow_1", "target": "ow_2", "sourceHandle": "Accepted" },
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
          "body": "{Thanks for connecting|Appreciate the connection}, {{first_name|there}}.\n\n{Our machine-learning model identified {{company|your company}} as a high-fit partner for our distributed workflow acceleration engine.|Based on your team's recent public milestones, {{company|your organization}} matches the profile of companies accelerating their outbound efficiency with our platform.}\n\n{Would you be open to a 5-minute technical briefing on how our Bayesian routing eliminates duplicate outreach across sales pods?|Open to comparing notes on how we can guarantee zero prospect collisions across your SDR teams?}"
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
          "subject": "{Strategic alignment for|Architectural review for} {{company|your team}} (Bayesian ICP match)",
          "body": "Hi {{first_name|there}},\n\nOur analytics platform flagged {{company|your company}}'s rapid expansion as an ideal fit for our account-based orchestration framework.\n\nGiven your leadership role, I wanted to share how we helped similar enterprise teams reduce lead acquisition cost by 38% while enforcing strict collision guards.\n\nDo you have 5 minutes for a brief introductory call this Thursday?\n\nBest,\n[Your Name]"
        }
      },
      {
        "id": "bn_1_end",
        "type": "sequence_end",
        "position": { "x": 450, "y": 250 },
        "data": {
          "delayDays": 0,
          "label": "Disqualify (Low Fit)",
          "exit_reason": "bad_fit"
        }
      }
    ],
    "edges": [
      { "id": "e_bn_1_2", "source": "bn_1", "target": "bn_2", "sourceHandle": "Strong fit (>75)" },
      { "id": "e_bn_1_end", "source": "bn_1", "target": "bn_1_end", "sourceHandle": "Weak fit (<75)" },
      { "id": "e_bn_2_3", "source": "bn_2", "target": "bn_3", "sourceHandle": "then" },
      { "id": "e_bn_3_4", "source": "bn_3", "target": "bn_4", "sourceHandle": "Accepted" },
      { "id": "e_bn_4_5", "source": "bn_4", "target": "bn_5", "sourceHandle": "Connected" },
      { "id": "e_bn_4_6", "source": "bn_4", "target": "bn_6", "sourceHandle": "Not connected" },
      { "id": "e_bn_6_7", "source": "bn_6", "target": "bn_7", "sourceHandle": "Found" }
    ]
  },
  {
    "id": "inbound_ghostwriter_omnichannel",
    "name": "Inbound Ghostwriter & Autonomous Omnichannel Engine",
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
          "body": "{Appreciate the connection|Great connecting with you}, {{first_name|there}}!\n\n{Your recent perspective on LinkedIn regarding industry operational scaling was exceptionally insightful.|Really appreciated your thoughtful analysis in your recent post — particularly your comments on team focus.}\n\n{Would love to stay in dialogue as both our teams navigate enterprise growth this year.|Looking forward to keeping in touch and learning from your updates!}"
        }
      },
      {
        "id": "ig_8",
        "type": "send_email",
        "position": { "x": 500, "y": 700 },
        "data": {
          "delayDays": 1,
          "label": "Multichannel Email Fallback",
          "subject": "{Connecting after your recent LinkedIn post|Continuing our LinkedIn thread} ({{first_name|there}})",
          "body": "Hi {{first_name|there}},\n\nI commented on your thoughtful LinkedIn post earlier this week and sent a connection invite.\n\nReaching out directly via email in case you check LinkedIn infrequently — would welcome the chance to exchange notes on {{company|your company}}'s strategic roadmap.\n\nAre you open to a brief 5-minute chat next week?\n\nBest,\n[Your Name]"
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
