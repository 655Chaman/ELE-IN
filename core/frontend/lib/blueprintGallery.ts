import { v4 as uuidv4 } from "uuid"
import type { SeqTreeNode, StickyNote } from "@campaigns/eiTreeStore"
import type { EleInBlueprint } from "./blueprintSchema"
import { fetchWithAuth } from "@/lib/apiClient"

// ─── Curated Agency-Grade Blueprints (Make.com & n8n Style Gallery) ─────────

export const CURATED_BLUEPRINTS: EleInBlueprint[] = [
  {
    schema: "elein-blueprint-v1",
    metadata: {
      name: "Tier-1 Enterprise AE Multichannel Cadence",
      description: "High-touch outreach for C-suite and VP buyers. Combines profile warmup, connection requests, and email fallback.",
      version: "1.2.0",
      schemaVersion: "elein-blueprint-v1",
      exportedAt: "2026-10-20T10:00:00.000Z",
      branding: {
        agencyName: "HyperScale Outbound",
        authorName: "Marcus Vance",
        accentColor: "#6366f1",
        badge: "Enterprise Verified",
        website: "https://hyperscaleoutbound.com",
      },
      tags: ["enterprise", "multichannel", "c-suite"],
      stats: {
        nodeCount: 6,
        actionCount: 4,
        conditionCount: 2,
        aiCount: 1,
        delayDaysTotal: 8,
        stickyNotesCount: 1,
        requiredVariables: ["first_name", "company", "job_title"],
        channels: ["linkedin", "email", "multichannel"],
      },
    },
    sequence: {
      rootNodes: [
        {
          id: "node_curated_1_1",
          type: "view_profile",
          data: { delayDays: 0, label: "Silent Profile Inspection" },
          children: {
            then: [
              {
                id: "node_curated_1_2",
                type: "connection_request",
                data: {
                  delayDays: 1,
                  note: "Hi {{first_name|there}}, saw your leadership at {{company|your team}} in {{job_title|your space}}. Would love to exchange notes.",
                  withdraw_enabled: true,
                },
                children: {
                  accepted: [
                    {
                      id: "node_curated_1_3",
                      type: "send_message",
                      data: {
                        delayDays: 1,
                        message: "Thanks for connecting, {{first_name|there}}! We recently put together a benchmark on pipeline velocity for {{job_title|leadership}}. Happy to share if relevant.",
                      },
                      children: {
                        then: [
                          {
                            id: "node_curated_1_4",
                            type: "if_replied",
                            data: { delayDays: 3 },
                            children: {
                              replied: [
                                {
                                  id: "node_curated_1_end1",
                                  type: "sequence_end",
                                  data: { label: "Goal Achieved: Positive Dialogue" },
                                  children: {},
                                },
                              ],
                              not_replied: [
                                {
                                  id: "node_curated_1_5",
                                  type: "send_email",
                                  data: {
                                    delayDays: 2,
                                    subject: "Quick question regarding {{company|your team}}'s outbound",
                                    message: "Hi {{first_name|there}},\n\nReaching out following our LinkedIn connection. Wanted to share the benchmark report we discussed.\n\nBest regards,\n[Your Name]",
                                  },
                                  children: {},
                                },
                              ],
                            },
                          },
                        ],
                      },
                    },
                  ],
                  ignored: [
                    {
                      id: "node_curated_1_end2",
                      type: "sequence_end",
                      data: { label: "Request Withdrawn Automatically" },
                      children: {},
                    },
                  ],
                },
              },
            ],
          },
        },
      ],
      stickyNotes: [
        {
          id: "sn_curated_1",
          x: 420,
          y: 40,
          text: "Strategy Note: Ensure your sender has at least 300+ connections before running C-level cadences.",
          title: "Enterprise Best Practice",
          color: "indigo",
          category: "strategy",
          isPinned: true,
          isCollapsed: false,
          updatedAt: "2026-10-20T10:00:00.000Z",
        },
      ],
    },
  },
  {
    schema: "elein-blueprint-v1",
    metadata: {
      name: "Blue Ocean Warmup & Social Selling Flow",
      description: "Low-friction trust builder. Warms up prospects by visiting profiles, liking recent posts, and endorsing skills before connecting.",
      version: "1.0.0",
      schemaVersion: "elein-blueprint-v1",
      exportedAt: "2026-10-20T10:00:00.000Z",
      branding: {
        agencyName: "SocialFlow Agency",
        authorName: "Elena Rostova",
        accentColor: "#06b6d4",
        badge: "High Acceptance (68%)",
        website: "https://socialflow.co",
      },
      tags: ["social-selling", "warmup", "high-acceptance"],
      stats: {
        nodeCount: 5,
        actionCount: 4,
        conditionCount: 1,
        aiCount: 0,
        delayDaysTotal: 4,
        stickyNotesCount: 1,
        requiredVariables: ["first_name", "company"],
        channels: ["linkedin"],
      },
    },
    sequence: {
      rootNodes: [
        {
          id: "node_curated_2_1",
          type: "view_profile",
          data: { delayDays: 0, label: "Initial Warmup Visit" },
          children: {
            then: [
              {
                id: "node_curated_2_2",
                type: "like_post",
                data: { delayDays: 1, quantity: 1 },
                children: {
                  then: [
                    {
                      id: "node_curated_2_3",
                      type: "endorse_skill",
                      data: { delayDays: 1, quantity: 1 },
                      children: {
                        then: [
                          {
                            id: "node_curated_2_4",
                            type: "connection_request",
                            data: {
                              delayDays: 1,
                              note: "Hey {{first_name|there}}, loved your recent posts. Great to see what you are building at {{company|your company}}!",
                              withdraw_enabled: true,
                            },
                            children: {
                              accepted: [
                                {
                                  id: "node_curated_2_5",
                                  type: "send_message",
                                  data: {
                                    delayDays: 1,
                                    message: "Thanks for accepting {{first_name|there}}! Looking forward to following your journey.",
                                  },
                                  children: {},
                                },
                              ],
                            },
                          },
                        ],
                      },
                    },
                  ],
                },
              },
            ],
          },
        },
      ],
      stickyNotes: [
        {
          id: "sn_curated_2",
          x: 400,
          y: 60,
          text: "Warmup touches trigger 3 native LinkedIn notifications before the connection invite lands. This boosts acceptance to ~68%.",
          title: "Conversion Anatomy",
          color: "cyan",
          category: "strategy",
          isPinned: true,
          isCollapsed: false,
          updatedAt: "2026-10-20T10:00:00.000Z",
        },
      ],
    },
  },
  {
    schema: "elein-blueprint-v1",
    metadata: {
      name: "Founder Direct Blitz (Ultra Short & Punchy)",
      description: "Fast-moving 2-step direct outreach for early-stage founders and executives who despise fluffy sales pitches.",
      version: "2.1.0",
      schemaVersion: "elein-blueprint-v1",
      exportedAt: "2026-10-20T10:00:00.000Z",
      branding: {
        agencyName: "Apex Growth Lab",
        authorName: "David Sterling",
        accentColor: "#10b981",
        badge: "Top Reply Rate",
        website: "https://apexgrowth.io",
      },
      tags: ["direct", "fast-cadence", "founders"],
      stats: {
        nodeCount: 4,
        actionCount: 3,
        conditionCount: 1,
        aiCount: 0,
        delayDaysTotal: 3,
        stickyNotesCount: 0,
        requiredVariables: ["first_name", "company"],
        channels: ["linkedin"],
      },
    },
    sequence: {
      rootNodes: [
        {
          id: "node_curated_3_1",
          type: "connection_request",
          data: {
            delayDays: 0,
            note: "Hi {{first_name|there}}, quick question regarding outbound scaling at {{company|your company}}. Open to connecting?",
            withdraw_enabled: true,
          },
          children: {
            accepted: [
              {
                id: "node_curated_3_2",
                type: "send_message",
                data: {
                  delayDays: 0,
                  message: "{{first_name|there}}, we built a system that books 15+ meetings/mo for teams like {{company|yours}} with zero manual research.\n\nWorth a 7-minute look?",
                },
                children: {
                  then: [
                    {
                      id: "node_curated_3_3",
                      type: "send_message",
                      data: {
                        delayDays: 3,
                        message: "No worries if timing is off, {{first_name|there}}. Should I circle back next month?",
                      },
                      children: {},
                    },
                  ],
                },
              },
            ],
          },
        },
      ],
    },
  },
  {
    schema: "elein-blueprint-v1",
    metadata: {
      name: "Hiring & Expansion Signal InMail Trigger",
      description: "Checks if company is hiring before firing an InMail. High relevance outbound tailored to expansion signals.",
      version: "1.1.0",
      schemaVersion: "elein-blueprint-v1",
      exportedAt: "2026-10-20T10:00:00.000Z",
      branding: {
        agencyName: "SignalPeak Intelligence",
        authorName: "Sarah Chen",
        accentColor: "#f59e0b",
        badge: "Signal Triggered",
        website: "https://signalpeak.ai",
      },
      tags: ["intent-signals", "hiring", "inmail"],
      stats: {
        nodeCount: 5,
        actionCount: 3,
        conditionCount: 2,
        aiCount: 0,
        delayDaysTotal: 4,
        stickyNotesCount: 1,
        requiredVariables: ["first_name", "company", "job_title"],
        channels: ["linkedin"],
      },
    },
    sequence: {
      rootNodes: [
        {
          id: "node_curated_4_1",
          type: "if_company_hiring",
          data: { delayDays: 0, label: "Check Active Job Openings" },
          children: {
            hiring: [
              {
                id: "node_curated_4_2",
                type: "send_inmail",
                data: {
                  delayDays: 0,
                  subject: "Scaling the {{job_title|engineering}} team at {{company|your company}}",
                  message: "Hi {{first_name|there}},\n\nSaw {{company|your company}} has active job openings. When scaling rapidly, onboarding speed is critical.\n\nWould it make sense to connect?",
                },
                children: {
                  then: [
                    {
                      id: "node_curated_4_3",
                      type: "if_replied",
                      data: { delayDays: 4 },
                      children: {
                        replied: [
                          {
                            id: "node_curated_4_end1",
                            type: "sequence_end",
                            data: { label: "Meeting Link Sent" },
                            children: {},
                          },
                        ],
                        not_replied: [
                          {
                            id: "node_curated_4_4",
                            type: "connection_request",
                            data: {
                              delayDays: 1,
                              note: "Sent a quick InMail regarding {{company|your company}}'s open roles, {{first_name|there}}. Thought I'd connect here as well.",
                              withdraw_enabled: true,
                            },
                            children: {},
                          },
                        ],
                      },
                    },
                  ],
                },
              },
            ],
            not_hiring: [
              {
                id: "node_curated_4_end2",
                type: "sequence_end",
                data: { label: "Paused: No Active Hiring Signals" },
                children: {},
              },
            ],
          },
        },
      ],
      stickyNotes: [
        {
          id: "sn_curated_4",
          x: 400,
          y: 40,
          text: "Hiring signals have a 3.4x higher conversion rate because teams have active budget allocations.",
          title: "Signal Data",
          color: "amber",
          category: "strategy",
          isPinned: true,
          isCollapsed: false,
          updatedAt: "2026-10-20T10:00:00.000Z",
        },
      ],
    },
  },
  {
    schema: "elein-blueprint-v1",
    metadata: {
      name: "Event & Webinar Attendee Harvester",
      description: "Engages leads who RSVPed to industry events or competitor webinars. References shared interests.",
      version: "1.0.0",
      schemaVersion: "elein-blueprint-v1",
      exportedAt: "2026-10-20T10:00:00.000Z",
      branding: {
        agencyName: "EventLeads Pro",
        authorName: "Liam O'Connor",
        accentColor: "#ec4899",
        badge: "Event Specialist",
        website: "https://eventleads.pro",
      },
      tags: ["events", "webinar", "intent-signals"],
      stats: {
        nodeCount: 4,
        actionCount: 3,
        conditionCount: 1,
        aiCount: 0,
        delayDaysTotal: 3,
        stickyNotesCount: 0,
        requiredVariables: ["first_name", "company"],
        channels: ["linkedin"],
      },
    },
    sequence: {
      rootNodes: [
        {
          id: "node_curated_5_1",
          type: "view_profile",
          data: { delayDays: 0, label: "Event Attendee Verification" },
          children: {
            then: [
              {
                id: "node_curated_5_2",
                type: "connection_request",
                data: {
                  delayDays: 0,
                  note: "Hi {{first_name|there}}, saw you also registered for the outbound summit. Would be great to connect with fellow attendees from {{company|your team}}!",
                  withdraw_enabled: true,
                },
                children: {
                  accepted: [
                    {
                      id: "node_curated_5_3",
                      type: "send_message",
                      data: {
                        delayDays: 1,
                        message: "Great to connect, {{first_name|there}}! What session are you looking forward to most? We prepared a key takeaways cheat sheet if you'd like a copy.",
                      },
                      children: {},
                    },
                  ],
                },
              },
            ],
          },
        },
      ],
    },
  },
  {
    schema: "elein-blueprint-v1",
    metadata: {
      name: "AI-Powered Personalization & Icebreaker Flow",
      description: "Generates custom AI icebreakers from lead profile summaries and recent posts before sending messages.",
      version: "1.3.0",
      schemaVersion: "elein-blueprint-v1",
      exportedAt: "2026-10-20T10:00:00.000Z",
      branding: {
        agencyName: "AI Outbound Systems",
        authorName: "Toby Thorne",
        accentColor: "#8b5cf6",
        badge: "AI Powered",
        website: "https://aioutbound.io",
      },
      tags: ["ai", "hyper-personalized", "c-suite"],
      stats: {
        nodeCount: 5,
        actionCount: 4,
        conditionCount: 1,
        aiCount: 1,
        delayDaysTotal: 5,
        stickyNotesCount: 1,
        requiredVariables: ["first_name", "company", "recent_post_topic"],
        channels: ["linkedin"],
      },
    },
    sequence: {
      rootNodes: [
        {
          id: "node_curated_6_1",
          type: "ai_personalize",
          data: {
            delayDays: 0,
            prompt: "Analyze profile and generate 1 crisp sentence praising their recent insight regarding {{recent_post_topic|their space}}.",
          },
          children: {
            then: [
              {
                id: "node_curated_6_2",
                type: "connection_request",
                data: {
                  delayDays: 0,
                  note: "Hi {{first_name|there}}, really appreciated your thoughts on {{recent_post_topic|industry trends}}. Would love to follow your work at {{company|your company}}.",
                  withdraw_enabled: true,
                },
                children: {
                  accepted: [
                    {
                      id: "node_curated_6_3",
                      type: "send_message",
                      data: {
                        delayDays: 1,
                        message: "Thanks for connecting, {{first_name|there}}. Given what you shared on {{recent_post_topic|this topic}}, I thought you might appreciate our recent study on scaling outbound.",
                      },
                      children: {
                        then: [
                          {
                            id: "node_curated_6_4",
                            type: "send_message",
                            data: {
                              delayDays: 4,
                              message: "Wanted to check if you had a chance to glance at that, {{first_name|there}}?",
                            },
                            children: {},
                          },
                        ],
                      },
                    },
                  ],
                },
              },
            ],
          },
        },
      ],
      stickyNotes: [
        {
          id: "sn_curated_6",
          x: 420,
          y: 50,
          text: "AI icebreakers reference real LinkedIn activity. This creates an authentic feel that bypasses lead resistance.",
          title: "AI Personalization",
          color: "purple",
          category: "strategy",
          isPinned: true,
          isCollapsed: false,
          updatedAt: "2026-10-20T10:00:00.000Z",
        },
      ],
    },
  },
]

// ─── Workspace Saved Blueprints (Layer 2 Paranoia) ──────────────────────────

const SAVED_BLUEPRINTS_KEY = "elein_workspace_blueprints_library"

export function getSavedWorkspaceBlueprints(): EleInBlueprint[] {
  try {
    const raw = localStorage.getItem(SAVED_BLUEPRINTS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveBlueprintToWorkspaceLibrary(blueprint: EleInBlueprint): void {
  const existing = getSavedWorkspaceBlueprints()
  // Check if blueprint with same name exists, replace or prepend
  const filtered = existing.filter(b => b.metadata.name.toLowerCase() !== blueprint.metadata.name.toLowerCase())
  const updated = [blueprint, ...filtered].slice(0, 30) // Max 30 saved blueprints
  try {
    localStorage.setItem(SAVED_BLUEPRINTS_KEY, JSON.stringify(updated))
  } catch (e) {
    console.warn("[Workspace Library] Failed to save blueprint", e)
  }
}

export function deleteBlueprintFromWorkspaceLibrary(name: string): void {
  const existing = getSavedWorkspaceBlueprints()
  const filtered = existing.filter(b => b.metadata.name.toLowerCase() !== name.toLowerCase())
  localStorage.setItem(SAVED_BLUEPRINTS_KEY, JSON.stringify(filtered))
}


// ─── Cloud Blueprints Sync (Phase 43 / Option B) ────────────────────────────

export async function fetchCloudBlueprints(): Promise<EleInBlueprint[]> {
  try {
    const res = await fetchWithAuth("/api/elein/blueprints")
    if (!res.ok) return []
    const rows = await res.json()
    if (!Array.isArray(rows)) return []

    return rows.map((r: any) => ({
      schema: r.schema_version || "elein-blueprint-v1",
      metadata: {
        id: r.id,
        name: r.name,
        description: r.description,
        version: r.version || "1.0.0",
        schemaVersion: r.schema_version || "elein-blueprint-v1",
        exportedAt: r.updated_at || r.created_at || new Date().toISOString(),
        branding: r.branding || {},
        tags: r.tags || ["cloud-synced"],
        stats: r.stats,
      },
      sequence: r.sequence_data || { rootNodes: [] },
    }))
  } catch (err) {
    console.warn("[Cloud Blueprints] Fetch failed, falling back to local library", err)
    return []
  }
}

export async function saveBlueprintToCloud(
  blueprint: EleInBlueprint
): Promise<{ success: boolean; data?: any; error?: string }> {
  try {
    const payload = {
      name: blueprint.metadata.name,
      description: blueprint.metadata.description,
      version: blueprint.metadata.version || "1.0.0",
      schema_version: blueprint.metadata.schemaVersion || "elein-blueprint-v1",
      branding: blueprint.metadata.branding || {},
      sequence_data: blueprint.sequence,
      stats: blueprint.metadata.stats,
      tags: blueprint.metadata.tags || [],
      is_public: false,
    }

    const res = await fetchWithAuth("/api/elein/blueprints", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      return { success: false, error: errData.detail || "Failed to save blueprint to cloud" }
    }

    const data = await res.json()
    return { success: true, data }
  } catch (e: any) {
    return { success: false, error: e.message || "Network error while saving to cloud" }
  }
}

export async function deleteBlueprintFromCloud(blueprintId: string): Promise<boolean> {
  try {
    const res = await fetchWithAuth(`/api/elein/blueprints/${blueprintId}`, {
      method: "DELETE",
    })
    return res.ok
  } catch {
    return false
  }
}
