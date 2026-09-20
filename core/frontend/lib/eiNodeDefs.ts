// ─────────────────────────────────────────────────────────────────────────────
// LinkedIn B2B Lead Generation — Full 100-Node Taxonomy
// Goal: Cold Lead → Warmed → Connected → Engaged → Meeting Booked
// ─────────────────────────────────────────────────────────────────────────────

export const HR_NODE_DEFS = {

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: WARM-UP (15 nodes)
  // Why: Cold connection requests = ~20% acceptance. Warmed = 40-50%.
  // Get your name seen 2-3 times before connecting.
  // ══════════════════════════════════════════════════════════════════════════

  view_profile: {
    label: "View Profile",
    description: "Visit the lead's profile to create a 'viewed your profile' notification. Warmed leads have a 40-50% higher connection acceptance rate. Best followed by a 1-2 day delay before sending a Connection Request.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  follow_profile: {
    label: "Follow Profile",
    description: "Follow their public profile to trigger a notification and make your posts visible to them. A great soft-touch entry point for enterprise targets before committing to a Connection Request.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 1,
    fields: [],
  },

  like_post: {
    label: "React to Post",
    description: "Like their most recent post to establish immediate relevance. Highly effective when run 2-3 days before connecting. Ensure you follow up with a 'View Profile' or a Connection Request.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "quantity", label: "Number of posts to react to", type: "number", default: 1, min: 1, max: 5 },
      { key: "reaction_type", label: "Reaction type", type: "select", options: ["Like", "Insightful", "Celebrate", "Support", "Funny"] },
      { key: "skip_promotional", label: "Smart Filter: Skip promotional & reposts", type: "toggle" },
    ],
  },

  comment_on_post: {
    label: "Comment on Post",
    description: "Leave a custom or AI-generated comment on their post. Comments are 5x more visible than likes. This is a high-intent warm-up action—follow with a Connection Request referencing the post.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 1,
    fields: [
      { key: "comment_mode", label: "Comment mode", type: "select", options: ["AI-generated (from post content)", "Fixed comment", "A/B test"] },
      { key: "comment", label: "Fixed comment (if not AI)", type: "textarea", maxChars: 1250, placeholder: "Really insightful perspective on {{topic}}...", hideIf: "comment_mode==AI-generated (from post content)" },
    ],
  },

  endorse_skill: {
    label: "Endorse a Skill",
    description: "Endorse one of their top skills. A highly visible, rarely automated action that instantly puts your face in their notifications. Wait 1 day, then connect.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "quantity", label: "Number of skills to endorse", type: "number", default: 1, min: 1, max: 5 },
      { key: "fallback", label: "If fewer skills available", type: "select", options: ["Endorse however many exist", "Skip this step"] },
    ],
  },

  follow_company: {
    label: "Follow Company Page",
    description: "Follow the lead's company page to signal deep research. This builds trust by showing you care about their organization, not just a quick sale. Follow up by engaging with their content.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  share_post: {
    label: "Share Their Post",
    description: "Share their post to your network. The ultimate form of engagement that guarantees a notification. They will remember your name. Follow up 2 days later with a Connection Request.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 1,
    fields: [
      { key: "share_comment", label: "Share caption", type: "textarea", maxChars: 3000, placeholder: "Really worth reading..." },
    ],
  },

  invite_to_event: {
    label: "LinkedIn Event Invite",
    description: "Invite the lead to a LinkedIn Event you are hosting. Delivers massive upfront value and builds authority before you even pitch. Follow up by messaging attendees.",
    category: "warmup",
    color: "#8b5cf6",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "event_url", label: "LinkedIn Event URL", type: "input", placeholder: "https://www.linkedin.com/events/..." },
      { key: "invite_note", label: "Invite note (optional)", type: "textarea", maxChars: 300, placeholder: "Hey {{first_name}}, hosting a quick session on X — think you'd find it valuable." },
    ],
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: CONNECTION (5 nodes)
  // ══════════════════════════════════════════════════════════════════════════

  connection_request: {
    label: "Send Connection Request",
    description: "Send a personalized connection request (max 300 chars). This is your primary entry into their inbox.",
    category: "connect",
    color: "#6366f1",
    outputs: ["Accepted", "Not Accepted Yet"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "note_strategy", label: "Note strategy", type: "select", options: ["No note", "Fixed note", "AI-generated note"] },
      { key: "note", label: "Connection note", type: "textarea", maxChars: 300, placeholder: "Hi {{first_name}}, saw your work at {{company}} — would love to connect!", showIf: "note_strategy==Fixed note" },
      { key: "ai_note_style", label: "AI note tone", type: "select", options: ["Professional", "Casual", "Direct", "Curiosity-based"], showIf: "note_strategy==AI-generated note" },
      { key: "ai_note_hook", label: "AI personalization hook", type: "select", options: ["Their recent post", "Their job title + company", "Mutual connection", "Company news"], showIf: "note_strategy==AI-generated note" },
      { key: "withdraw_enabled", label: "Auto-withdraw if not accepted", type: "toggle" },
      { key: "withdraw_days", label: "Withdraw after (days)", type: "number", default: 21, min: 1, max: 90, showIf: "withdraw_enabled==true" },
      { key: "fallback_info", label: "No-note Fallback", type: "info", content: "LinkedIn limits personalized connection invites on non-premium accounts. When an account reaches its limit, we'll still send the invite - just without the note." },
    ],
    versioned: true,
  },

  withdraw_request: {
    label: "Withdraw Pending Request",
    description: "Auto-withdraw a connection request if pending for N days. Keeps your LinkedIn account safe from spam flags. If withdrawn, route the lead to a cold email sequence.",
    category: "connect",
    color: "#6366f1",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 21,
    fields: [
      { key: "days_pending", label: "Withdraw after (days)", type: "number", default: 21, min: 1, max: 90 },
    ],
  },

  remove_connection: {
    label: "Remove Connection",
    description: "Remove a 1st-degree connection. Use this to clean up your network for bad-fit leads or after a hard opt-out to maintain a high-quality feed.",
    category: "connect",
    color: "#6366f1",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: CONDITIONS (20 nodes)
  // Every unguarded path wastes your daily LinkedIn limit.
  // ══════════════════════════════════════════════════════════════════════════

  if_connected: {
    label: "If Connected?",
    description: "Checks if the lead accepted your connection. This is the most critical branch in any sequence. Route to a 'Send Message' on the YES path, and an Email/InMail fallback on the NO path.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Connected", "Not connected"],
    hasDelay: true,
    delayDefault: 3,
    fields: [],
  },



  if_phone_found: {
    label: "If Phone Found?",
    description: "Checks if a direct dial was found. Route to a 'Slack Alert' to notify an SDR to call them immediately while they are engaged.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Phone found", "Not found"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  open_profile_check: {
    label: "Open Profile Check",
    description: "Checks if their profile is open to free InMails. If YES, skip the connection request and send a direct InMail to save time and credits.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Open", "Not open"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  if_large_following: {
    label: "If High Follower Count?",
    description: "Checks if the lead has more than N followers. Profiles with massive followings (e.g., Creators) often require you to follow them before you can connect. Route high-follower profiles to a 'Follow Profile' or 'InMail' path.",
    category: "conditions",
    color: "#10b981",
    outputs: ["High following", "Normal following"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "follower_threshold", label: "Follower threshold", type: "number", default: 10000 },
    ],
  },

  if_premium_member: {
    label: "If LinkedIn Premium?",
    description: "Checks if they have LinkedIn Premium. Premium members are typically decision-makers with budget. Route them to a high-priority, highly-personalized messaging track.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Premium", "Free"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  if_mutual_connections: {
    label: "If Mutual Connections?",
    description: "Checks for mutual connections. Shared connections drastically improve trust. If YES, trigger an 'AI Personalize' node to mention the mutual connection in your opener.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Has mutuals", "No mutuals"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "min_mutuals", label: "Minimum mutual connections", type: "number", default: 1 },
    ],
  },

  if_recently_active: {
    label: "If Recently Active?",
    description: "Checks if they were active in the last 7 days. Skip inactive leads to save your daily limits, or route them directly to cold email instead of LinkedIn.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Active", "Inactive"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "days", label: "Active within (days)", type: "number", default: 7 },
    ],
  },

  if_has_recent_posts: {
    label: "If Has Recent Posts?",
    description: "Checks if they posted recently. Active posters are much easier to warm up. Route to 'Comment on Post' if YES, or 'View Profile' if NO.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Has posts", "No posts"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "days", label: "Posted in last (days)", type: "number", default: 30 },
    ],
  },

  if_company_hiring: {
    label: "If Company is Hiring?",
    description: "Detects if the company has open job postings. Hiring signals budget and growth. Route these leads to a more aggressive, pain-point-focused pitch.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Hiring", "Not hiring"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "role_keywords", label: "Role keywords (optional filter)", type: "input", placeholder: "Sales, Marketing, Engineer" },
    ],
  },

  icp_score_gate: {
    label: "ICP Score Gate",
    description: "Scores the lead based on title, size, and activity. Only allow high-scoring leads (e.g., >75) to proceed to expensive manual tasks or premium InMails.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Strong fit (>75)", "Weak fit (<75)"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "score_threshold", label: "Minimum score (0-100)", type: "number", default: 75 },
      { key: "weight_title", label: "Title match weight", type: "number", default: 30 },
      { key: "weight_size", label: "Company size weight", type: "number", default: 25 },
      { key: "weight_industry", label: "Industry weight", type: "number", default: 25 },
      { key: "weight_activity", label: "LinkedIn activity weight", type: "number", default: 20 },
    ],
  },

/*
  if_meeting_booked: {
    label: "If Meeting Booked?",
    description: "Checks if they booked via your Calendly link. This is a critical safety net. If YES, route to 'Mark Converted' and stop all further automated follow-ups.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Booked", "Not booked"],
    hasDelay: true,
    delayDefault: 2,
    fields: [],
  },
*/



  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: DIRECT MESSAGES (12 nodes)
  // ══════════════════════════════════════════════════════════════════════════

  send_message: {
    label: "Send Message",
    description: "Send a standard LinkedIn DM. 80% of sales require 5 follow-ups. Keep it conversational. ",
    category: "messages",
    color: "#6366f1",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 1,
    fields: [
      { key: "body", label: "Message body", type: "textarea", maxChars: 8000, placeholder: "Hey {{first_name}}, ..." },
      { key: "fallback", label: "Fallback message", type: "textarea", maxChars: 8000, placeholder: "Fallback if primary fails..." },
      { key: "variant_b", label: "Variant B (optional A/B test)", type: "textarea", maxChars: 8000, placeholder: "Alternative version..." },
      { key: "variant_c", label: "Variant C (optional)", type: "textarea", maxChars: 8000, placeholder: "Third variant..." },
      { key: "attachment_type", label: "Attachment", type: "select", options: ["None", "Document", "Image"] },
      { key: "attachment_url", label: "Attachment URL", type: "input", placeholder: "https://...", showIf: "attachment_type!=None" },
    ],
    versioned: true,
  },

  send_ai_message: {
    label: "Send AI-Personalized Message",
    description: "AI drafts a highly personalized message using their recent activity. Yields the highest reply rates. Follow with an 'If Replied?' condition.",
    category: "messages",
    color: "#6366f1",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 1,
    fields: [
      { key: "pitch", label: "What is the goal of this message?", type: "textarea", maxChars: 7000, placeholder: "Just talk to the AI! (e.g., 'I want to see if they need help with lead gen, and if they do, offer a quick 10-minute chat.')", helperText: `Examples:
• "See if they are hiring engineers. If yes, pitch our recruitment platform."
• "Ask if they struggle with CRM data entry. Our AI agent solves this."
• "Congratulate them on their new role and gently introduce our analytics tool."` },
      { key: "tone", label: "How should the AI sound?", type: "select", options: ["Friendly & Casual", "Professional & Direct", "Short & Punchy", "Funny & Witty"] },
      { key: "ai_model", label: "AI Routing Engine (Model)", type: "select", options: ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"], default: "Auto-Route (Recommended)" },
    ],
  },

  send_voice_note: {
    label: "Send Voice Note",
    description: "Send a pre-recorded voice note. 3x higher reply rate than text. Perfect for high-value leads. Follow up with a text bump a day later.",
    category: "messages",
    color: "#6366f1",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 2,
    fields: [
      { key: "audio_url", label: "Audio file URL", type: "input", placeholder: "https://... (mp3/wav, max 5min)" },
    ],
  },

  send_inmail: {
    label: "Send InMail",
    description: "Send a standard InMail using premium credits. Guaranteed delivery even without a connection. ",
    category: "messages",
    color: "#6366f1",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "subject", label: "Subject", type: "input", maxChars: 200, placeholder: "Quick thought on {{company}}" },
      { key: "body", label: "Body", type: "textarea", maxChars: 1900, placeholder: "Hi {{first_name}}, ..." },
    ],
    versioned: true,
  },

  send_paid_inmail: {
    label: "Send Paid InMail (Sponsored)",
    description: "Send a sponsored InMail. Extremely high delivery rate. Best used for tier-1 accounts that cannot be reached otherwise.",
    category: "messages",
    color: "#6366f1",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "subject", label: "Subject", type: "input", maxChars: 200, placeholder: "{{first_name}}, quick question" },
      { key: "body", label: "Body", type: "textarea", maxChars: 1900, placeholder: "Hi {{first_name}}, ..." },
    ],
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: AI-POWERED (10 nodes)
  // These are the actual moat. Nobody has these natively.
  // ══════════════════════════════════════════════════════════════════════════

  ai_personalize: {
    label: "AI Personalize",
    description: "AI generates a unique icebreaker variable based on their profile. Insert this variable into your message templates to automate deep personalization.",
    category: "ai",
    color: "#f97316",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "hook_sources", label: "What to pull from", type: "select", options: ["Recent post", "Job title + company", "Bio summary", "Company news", "Best available"] },
      { key: "hook_length", label: "Hook length", type: "select", options: ["One sentence", "Two sentences", "One line (punchy)"] },
      { key: "ai_model", label: "AI Routing Engine (Model)", type: "select", options: ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"], default: "Auto-Route (Recommended)" },
      { key: "custom_persona", label: "Custom Persona Override", type: "textarea", placeholder: "e.g., You are an aggressive tech recruiter..." },
      { key: "custom_rules", label: "Custom Generation Rules", type: "textarea", placeholder: "e.g., Write exactly 4 sentences. Be sarcastic." },
      { key: "fallback_message", label: "Fallback Message (If AI Fails)", type: "input", default: "" }],
  },

  ai_detect_sentiment: {
    label: "AI Detect Reply Sentiment",
    description: "AI categorizes their reply as Positive, Negative, or Neutral. Automates triage so your team only handles warm leads. Route each sentiment to a specific CRM action.",
    category: "ai",
    color: "#f97316",
    outputs: ["Positive", "Neutral", "Negative"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  ai_generate_icebreaker: {
    label: "AI Generate Icebreaker",
    description: "AI writes a custom comment or opening line referencing their latest post. Incredibly effective for starting organic conversations.",
    category: "ai",
    color: "#f97316",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "tone", label: "Icebreaker tone", type: "select", options: ["Curious", "Agreeable", "Challenging (respectfully)", "Complimentary"] },
      { key: "max_chars", label: "Max length (chars)", type: "number", default: 150 },
      { key: "ai_model", label: "AI Routing Engine (Model)", type: "select", options: ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"], default: "Auto-Route (Recommended)" },
      { key: "custom_persona", label: "Custom Persona Override", type: "textarea", placeholder: "e.g., You are an aggressive tech recruiter..." },
      { key: "custom_rules", label: "Custom Generation Rules", type: "textarea", placeholder: "e.g., Write exactly 4 sentences. Be sarcastic." },
      { key: "fallback_message", label: "Fallback Message (If AI Fails)", type: "input", default: "" }],
  },

  ai_translate_message: {
    label: "AI Translate Message",
    description: "Auto-translates your message into the lead's native language. Essential for global campaigns—native languages convert at 2x the rate.",
    category: "ai",
    color: "#f97316",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "fallback_language", label: "Fallback language", type: "select", options: ["English", "Spanish", "French", "German", "Portuguese", "Dutch"] },
      { key: "ai_model", label: "AI Routing Engine (Model)", type: "select", options: ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"], default: "Auto-Route (Recommended)" },
      { key: "custom_persona", label: "Custom Persona Override", type: "textarea", placeholder: "e.g., You are an aggressive tech recruiter..." },
      { key: "custom_rules", label: "Custom Generation Rules", type: "textarea", placeholder: "e.g., Write exactly 4 sentences. Be sarcastic." },
      { key: "fallback_message", label: "Fallback Message (If AI Fails)", type: "input", default: "" }],
  },

  ai_score_icp: {
    label: "AI Score ICP Fit",
    description: "AI grades the lead against your ideal customer profile. Use this to filter out bad fits dynamically before sending them any messages.",
    category: "ai",
    color: "#f97316",
    outputs: ["High fit (>75)", "Medium fit (50-75)", "Low fit (<50)"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "icp_description", label: "Your ICP description", type: "textarea", maxChars: 500, placeholder: "B2B SaaS founders and VPs of Sales at companies 20-200 employees who are scaling outbound..." },
      { key: "ai_model", label: "AI Routing Engine (Model)", type: "select", options: ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"], default: "Auto-Route (Recommended)" },
      { key: "custom_persona", label: "Custom Persona Override", type: "textarea", placeholder: "e.g., You are an aggressive tech recruiter..." },
      { key: "custom_rules", label: "Custom Generation Rules", type: "textarea", placeholder: "e.g., Write exactly 4 sentences. Be sarcastic." },
      { key: "fallback_message", label: "Fallback Message (If AI Fails)", type: "input", default: "" }],
  },

/*
  ai_buying_signal: {
    comingSoon: true,
    label: "AI Detect Buying Signal",
    description: "AI scans their recent posts for specific buying signals or pain points. Route high-signal leads directly to an SDR via a Slack Alert.",
    category: "ai",
    color: "#f97316",
    outputs: ["Signal detected", "No signal"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "signal_keywords", label: "Signal topics (what pain do you solve?)", type: "textarea", maxChars: 300, placeholder: "outbound, pipeline, lead gen, sales team, hiring SDRs, scaling revenue..." },
    ],
  },
*/

/*
  ai_write_connection_note: {
    comingSoon: true,
    label: "AI Write Connection Note",
    description: "AI drafts a personalized connection note based on shared interests or career history. Avoids generic templates and spikes acceptance rates.",
    category: "ai",
    color: "#f97316",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "angle", label: "Connection angle", type: "select", options: ["Relevant experience", "Shared interest in their post", "Company context", "Direct value offer"] },
    ],
  },
*/

  ai_summarize_profile: {
    label: "AI Summarize Profile",
    description: "Creates a concise 'intel card' about the lead. Automatically pushes to your CRM so your sales team has full context before the demo call.",
    category: "ai",
    color: "#f97316",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "ai_model", label: "AI Routing Engine (Model)", type: "select", options: ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"], default: "Auto-Route (Recommended)" },
      { key: "custom_persona", label: "Custom Persona Override", type: "textarea", placeholder: "e.g., You are an aggressive tech recruiter..." },
      { key: "custom_rules", label: "Custom Generation Rules", type: "textarea", placeholder: "e.g., Write exactly 4 sentences. Be sarcastic." },
      { key: "fallback_message", label: "Fallback Message (If AI Fails)", type: "input", default: "" }
    ],
  },

  ai_detect_competitor: {
    label: "AI Detect Competitor User",
    description: "AI checks if the lead is currently using a competitor. If YES, route them to a specialized 'switch campaign' highlighting your unique advantages.",
    category: "ai",
    color: "#f97316",
    outputs: ["Using competitor", "Not detected"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "competitors", label: "Competitor names (comma-separated)", type: "input", placeholder: "EleIn, Lemlist, Apollo, Outreach..." },
      { key: "ai_model", label: "AI Routing Engine (Model)", type: "select", options: ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"], default: "Auto-Route (Recommended)" },
      { key: "custom_persona", label: "Custom Persona Override", type: "textarea", placeholder: "e.g., You are an aggressive tech recruiter..." },
      { key: "custom_rules", label: "Custom Generation Rules", type: "textarea", placeholder: "e.g., Write exactly 4 sentences. Be sarcastic." },
      { key: "fallback_message", label: "Fallback Message (If AI Fails)", type: "input", default: "" }],
  },

  ai_best_send_time: {
    label: "AI Suggest Best Send Time",
    description: "Analyzes their activity patterns and delays your message until they are actually online. Can increase open rates by up to 30%.",
    category: "ai",
    color: "#f97316",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "max_wait_hours", label: "Max wait window (hours)", type: "number", default: 24 },
    ],
  },

  // ══════════════════════════════════════════════════════════════════════════
  
  ai_generate_reply: {
    label: "AI: Reply to Lead",
    description: "Autonomously generate and send a context-aware reply to the lead's latest message based on your Workspace Knowledge Base (RAG). Highly effective after an 'If Replied' split.",
    category: "ai",
    color: "#f97316",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  ai_query_knowledge_base: {
    label: "AI Query Brain",
    description: "Queries the Workspace Knowledge Base about your business to generate a targeted objection-handling response based on a negative or questioning reply.",
    category: "ai",
    color: "#f97316",
    outputs: ["Response Generated", "Failed"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: DATA ENRICHMENT (12 nodes)
  // ══════════════════════════════════════════════════════════════════════════

  find_email: {
    comingSoon: true,
    label: "Find Work Email",
    description: "Runs a waterfall enrichment (Apollo -> Hunter -> Clearbit) to find a verified work email. Always follow this with an 'If Email Found?' condition.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Found", "Not found"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  find_personal_email: {
    comingSoon: true,
    label: "Find Personal Email",
    description: "Enriches their private email. Great for founder-to-founder outreach or when work emails bounce. Follow with an email campaign handoff.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Found", "Not found"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  find_phone: {
    comingSoon: true,
    label: "Find Phone Number",
    description: "Finds a direct dial or mobile number. If successful, route to a Slack Alert so your SDR team can execute a warm cold-call immediately.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Found", "Not found"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  find_tech_stack: {
    comingSoon: true,
    label: "Find Company Tech Stack",
    description: "Detects the software tools their company uses. Use this to dynamically branch your messaging (e.g., 'Saw you use Salesforce...').",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Found", "Not found"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "target_tools", label: "Tools to detect (optional)", type: "input", placeholder: "Salesforce, HubSpot, Stripe, Intercom..." },
    ],
  },

  find_funding_round: {
    comingSoon: true,
    label: "Find Funding Round",
    description: "Checks if they recently raised capital. Fresh funding means active budgets. Route funded companies to a high-priority outreach track.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Recently funded", "No recent funding"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "recency_months", label: "Funded in last (months)", type: "number", default: 12 },
    ],
  },

  find_headcount: {
    comingSoon: true,
    label: "Find Company Headcount",
    description: "Scrapes their exact employee count. Use this alongside an 'If Company Size' condition to ensure you aren't pitching to companies that are too small.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Found", "Not found"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  find_job_postings: {
    comingSoon: true,
    label: "Find Open Job Postings",
    description: "Detects open roles at their company. A strong indicator of growth and specific pain points. Route to a tailored pitch addressing their hiring needs.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Hiring", "Not hiring"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "role_filter", label: "Role keywords (optional)", type: "input", placeholder: "Sales, Marketing, Growth" },
    ],
  },

  get_linkedin_activity: {
    comingSoon: true,
    label: "Get LinkedIn Activity Score",
    description: "Scores how active they are on LinkedIn. Highly active leads should be engaged via comments and DMs; inactive leads should be routed to cold email.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Active (>4 posts/month)", "Passive (1-4)", "Inactive (<1)"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  get_mutual_connections: {
    comingSoon: true,
    label: "Get Mutual Connections",
    description: "Fetches shared connections. If found, route to an 'AI Personalize' node to dynamically drop a mutual connection's name in your opener.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Has mutuals", "No mutuals"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  verify_email: {
    comingSoon: true,
    label: "Verify Email Deliverability",
    description: "Pings the enriched email to ensure it won't bounce. Always run this before handing the lead off to an email sequencer to protect your domain reputation.",
    category: "enrichment",
    color: "#f59e0b",
    outputs: ["Valid", "Invalid / Risky"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: MULTICHANNEL HANDOFF (12 nodes)
  // ══════════════════════════════════════════════════════════════════════════

  send_slack_alert: {
    comingSoon: true,
    label: "Send Slack Alert",
    description: "Fires a real-time Slack notification to your team. Use this immediately when a lead replies positively, books a meeting, or is marked SQL.",
    category: "multichannel",
    color: "#ec4899",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "channel", label: "Slack channel", type: "input", placeholder: "#sales-signals" },
      { key: "message", label: "Alert message", type: "textarea", maxChars: 500, placeholder: "🔥 {{first_name}} from {{company}} replied to your LinkedIn sequence!" },
    ],
  },

  send_webhook: {
    comingSoon: true,
    label: "Send Webhook",
    description: "Sends lead data via POST request to Zapier, Make, or a custom backend. The ultimate escape hatch for custom integrations.",
    category: "multichannel",
    color: "#ec4899",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "url", label: "Webhook URL", type: "input", placeholder: "https://hooks.zapier.com/..." },
      { key: "payload_template", label: "Payload (JSON template)", type: "textarea", maxChars: 2000, placeholder: '{"name": "{{first_name}}", "company": "{{company}}"}' },
    ],
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: MEETING & CONVERSION (8 nodes)
  // ══════════════════════════════════════════════════════════════════════════

  send_meeting_invite: {
    label: "Send Meeting Invite",
    description: "Sends your Calendly link in a message. The sequence will automatically track this and halt if the meeting is booked.",
    category: "convert",
    color: "#f59e0b",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 3,
    fields: [
      { key: "calendly_url", label: "Calendly / Booking URL", type: "input", placeholder: "https://calendly.com/your-link" },
      { key: "body", label: "Message body", type: "textarea", maxChars: 8000, placeholder: "{{first_name}}, worth a 20-min call to see if there's a fit?" },
    ],
    versioned: true,
  },

  send_intro_call_invite: {
    label: "LinkedIn Intro Call Invite",
    description: "Sends a native LinkedIn meeting request. A low-friction alternative to external links. Follow up if they accept.",
    category: "convert",
    color: "#f59e0b",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 1,
    fields: [
      { key: "subject", label: "Meeting subject", type: "input", placeholder: "Quick intro call — 20 mins" },
      { key: "body", label: "Meeting note", type: "textarea", maxChars: 300, placeholder: "{{first_name}}, would love to connect — agenda: [X, Y, Z]" },
      { key: "duration_minutes", label: "Duration (minutes)", type: "number", default: 20 },
    ],
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CATEGORY: SEQUENCE CONTROL & LOGIC (6 nodes)
  // ══════════════════════════════════════════════════════════════════════════

  ab_split: {
    label: "A/B Split (50/50)",
    description: "Splits the sequence into Path A and Path B. Use this to continuously test subject lines, messages, or timing to optimize your conversion rates.",
    category: "control",
    color: "#52525b",
    outputs: ["Path A", "Path B"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  weighted_split: {
    label: "Weighted Split",
    description: "Splits traffic unevenly (e.g., 90/10). Use this to slowly roll out a new, experimental message track without risking your main pipeline.",
    category: "control",
    color: "#52525b",
    outputs: ["Path A", "Path B"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "path_a_pct", label: "Path A percentage (%)", type: "number", default: 50 },
    ],
  },

  daily_limit_check: {
    label: "Daily Limit Check",
    description: "Safety check to ensure you haven't hit LinkedIn's action limits. If full, it pauses the lead until tomorrow to protect your account.",
    category: "control",
    color: "#52525b",
    outputs: ["Under limit", "Limit reached"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "action_type", label: "Action type limit to check", type: "select", options: ["Connection requests", "Messages", "Profile views", "All actions"] },
    ],
  },

  blacklist_check: {
    label: "Blacklist Check",
    description: "Verifies the lead isn't on your global suppression list before acting. Essential safety node to prevent embarrassing double-outreach.",
    category: "control",
    color: "#52525b",
    outputs: ["Not blacklisted", "Blacklisted → skip"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  add_tag: {
    label: "Add Tag / Label",
    description: "Applies a custom tag to the lead for segmentation (e.g., 'ghosted', 'high-intent'). Useful for filtering leads in future retargeting campaigns.",
    category: "control",
    color: "#52525b",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "tag", label: "Tag name", type: "input", placeholder: "e.g. warm_lead, enterprise_prospect, conference_2025" },
    ],
  },

  sequence_end: {
    label: "Sequence End",
    description: "Terminates the path. Always define an exit reason (e.g., 'Unresponsive', 'Meeting Booked') so your analytics can track campaign performance accurately.",
    category: "control",
    color: "#52525b",
    outputs: [],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "exit_reason", label: "Exit reason", type: "select", options: ["unresponsive", "not_interested", "meeting_booked", "replied_positive", "replied_negative", "opted_out", "blacklisted", "bad_fit", "other"] },
    ],
  },


  retry_step: {
    label: "Retry Step",
    description: "Retries the previous step if it failed (e.g., if a tool call or AI generation failed). Prevents the sequence from breaking.",
    category: "control",
    color: "#52525b",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 1,
    fields: [
      { key: "max_retries", label: "Max retries", type: "number", default: 3 },
    ],
  },


  if_replied: {
    label: "If Replied?",
    description: "Branches based on the lead's reply sentiment, detected by AI. Routes to Positive, Negative, Neutral, or No Reply paths.",
    category: "conditions",
    color: "#6366f1",
    outputs: ["Positive", "Negative", "Neutral", "No Reply"],
    hasDelay: true,
    delayDefault: 0,
    fields: [],
  },

  push_to_crm: {
    label: "Push to CRM",
    description: "Syncs this lead to your connected CRM with all enriched data, notes, and sequence activity.",
    category: "multichannel",
    color: "#0ea5e9",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "provider", label: "CRM provider", type: "select", options: ["HubSpot", "Salesforce", "Pipedrive", "Notion", "Airtable"] },
      { key: "pipeline_stage", label: "Pipeline stage (optional)", type: "input", placeholder: "e.g. New Lead, Contacted" },
    ],
  },

  add_to_email_sequencer: {
    label: "Add to Email Sequencer",
    description: "Hands the lead off to a cold email tool to continue outreach via email in parallel.",
    category: "multichannel",
    color: "#0ea5e9",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "provider", label: "Email sequencer", type: "select", options: ["Smartlead", "Instantly", "EmailBison", "Lemlist", "Apollo"] },
      { key: "sequence_id", label: "Sequence ID", type: "input", placeholder: "Your sequence ID from the platform" },
    ],
  },

  update_lead_status: {
    label: "Update Lead Status",
    description: "Tags the lead with a lifecycle status. Used for analytics, CRM sync, and downstream routing.",
    category: "convert",
    color: "#f59e0b",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "status", label: "New status", type: "select", options: ["Interested", "MQL", "SQL", "Meeting Booked", "Converted", "Not Interested", "Opted Out (GDPR)", "Ghosted", "Bad Fit"] },
    ],
  },

  if_lead_matches: {
    label: "If Lead Matches Criteria?",
    description: "Filters leads by firmographic attributes. All enabled criteria must match (AND logic).",
    category: "conditions",
    color: "#6366f1",
    outputs: ["Matches", "No match"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "title_keywords", label: "Title contains (comma-separated, optional)", type: "input", placeholder: "CEO, Founder, VP Sales" },
      { key: "locations", label: "Location is (comma-separated, optional)", type: "input", placeholder: "United States, United Kingdom" },
      { key: "industries", label: "Industry is (comma-separated, optional)", type: "input", placeholder: "SaaS, Fintech, Healthcare" },
      { key: "min_headcount", label: "Min company headcount (optional)", type: "number", min: 1 },
      { key: "max_headcount", label: "Max company headcount (optional)", type: "number", max: 100000 },
    ],
  },


  send_email: {
    label: "Send Email",
    description: "Sends an email to the lead using SendGrid.",
    category: "messages",
    color: "#ec4899",
    outputs: ["then"],
    hasDelay: true,
    delayDefault: 0,
    fields: [
      { key: "to", label: "To (optional, defaults to lead's email)", type: "input", placeholder: "{{lead.email}}" },
      { key: "subject_template", label: "Subject", type: "input", placeholder: "e.g. Quick question..." },
      { key: "body_template", label: "Body", type: "textarea", placeholder: "e.g. Hi {{lead.first_name}}..." },
    ],
  },

  if_email_found: {
    label: "If Email Found?",
    description: "Branches based on whether the lead has a valid email address.",
    category: "conditions",
    color: "#10b981",
    outputs: ["Has Email", "No Email"],
    hasDelay: false,
    delayDefault: 0,
    fields: [],
  },
} as const

export type EINodeType = keyof typeof HR_NODE_DEFS

// ─── Category display config ───────────────────────────────────────────────────
export const HR_CATEGORY_LABELS: Record<string, string> = {
  warmup:       "Warm-up actions",
  connect:      "Connection",
  conditions:   "Conditions & branching",
  messages:     "Direct messages",
  ai:           "AI-powered",
  enrichment:   "Data enrichment",
  convert:      "Meeting & conversion",
  multichannel: "Multichannel handoff",
  control:      "Sequence control",
}

export const HR_CATEGORY_ORDER = [
  "warmup",
  "connect",
  "conditions",
  "messages",
  "ai",
  "convert",
  "enrichment",
  "multichannel",
  "control",
]

// ─── Color by category ─────────────────────────────────────────────────────────
export const HR_CATEGORY_COLORS: Record<string, string> = {
  warmup:       "#8b5cf6",
  connect:      "#6366f1",
  conditions:   "#10b981",
  messages:     "#6366f1",
  ai:           "#f97316",
  convert:      "#f59e0b",
  enrichment:   "#f59e0b",
  multichannel: "#ec4899",
  control:      "#52525b",
}
