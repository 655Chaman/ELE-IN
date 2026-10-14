export interface SimulatedMessage {
  id: string;
  sender_name: string;
  message_text: string;
  direction: 'inbound' | 'outbound';
  created_at: string;
}

export interface SimulatedIntentChip {
  label: string;
  intent: string;
  desc: string;
  suggestedDraft: string;
}

export interface SimulatedScenario {
  id: string;
  threadKey: string;
  senderName: string;
  title: string;
  company: string;
  campaignName: string;
  avatarInitials: string;
  avatarColor: string;
  badge: string;
  badgeClass: string;
  objectionType: 'budget' | 'competitor' | 'authenticity';
  initialOutcome: 'NOT_INTERESTED' | 'FOLLOW_UP' | 'INTERESTED';
  funding?: string;
  headcount?: string;
  techStack?: string[];
  dealValue?: string;
  linkedInUrl?: string;
  strategyRationale?: string;
  timingIntent?: {
    snoozeDateText: string;
    reason: string;
    suggestedCheckIn: string;
  };
  messages: SimulatedMessage[];
  intentChips: SimulatedIntentChip[];
  simulatedProspectFollowUp: {
    message_text: string;
    resultingOutcome: 'MEETING_BOOKED' | 'INTERESTED' | 'FOLLOW_UP';
    celebrationText: string;
  };
}

export const SIMULATED_SCENARIOS: SimulatedScenario[] = [
  {
    id: 'scenario-budget-freeze',
    threadKey: 'sim-alex-mercer',
    senderName: 'Alex Mercer',
    title: 'VP of Sales Operations',
    company: 'CloudScale Labs',
    campaignName: 'Q4 SaaS SDR Outbound',
    avatarInitials: 'AM',
    avatarColor: 'bg-muted text-foreground border border-border',
    badge: 'Budget Freeze',
    badgeClass: 'bg-muted text-foreground border-border font-medium',
    objectionType: 'budget',
    initialOutcome: 'FOLLOW_UP',
    funding: 'Series B ($28M)',
    headcount: '85 Employees',
    techStack: ['Salesforce', 'Outreach'],
    dealValue: '$18k ARR',
    linkedInUrl: 'https://linkedin.com/in/alex-mercer-salesops',
    strategyRationale: 'Executive budget freeze through Q3. Offer zero-spend benchmark audit to generate real performance data before Q4 planning.',
    timingIntent: {
      snoozeDateText: 'Nov 1',
      reason: 'Executive budget freeze active through Q3 - Alex requested November check-in',
      suggestedCheckIn: "Appreciate the candor, Alex! I've marked a follow-up for Nov 1 when Q4 planning opens up. Looking forward to reconnecting then!"
    },
    messages: [
      {
        id: 'sim-msg-1',
        sender_name: 'You',
        message_text: "Hey Alex, noticed CloudScale expanded your SDR pod last month. Most sales ops leaders we talk to see reps spending 14+ hrs/week wrestling with unverified lists and high bounce rates. We built Ele-in to run residential-jitter outreach with live Bayesian ICP scoring. Open to seeing a 2-min breakdown?",
        direction: 'outbound',
        created_at: new Date(Date.now() - 3 * 86400000).toISOString()
      },
      {
        id: 'sim-msg-2',
        sender_name: 'Alex Mercer',
        message_text: "Hey! The workflow actually sounds neat, but our executive leadership placed an immediate freeze on all new software spend through Q3. Can't commit any budget right now. Feel free to ping back in November.",
        direction: 'inbound',
        created_at: new Date(Date.now() - 3600000).toISOString()
      }
    ],
    intentChips: [
      {
        label: 'Free Data Benchmark (Zero Spend)',
        intent: 'free_pilot',
        desc: 'Pivot to free 25-lead test to benchmark against current stack',
        suggestedDraft: "Totally respect that, Alex — completely understand the Q3 budget hold. Rather than a paid rollout, would you be open to running 25 free leads through our Bayesian engine just to benchmark deliverability vs your current stack? Zero spend required, and you'll have real performance data ready for November planning. Let me know if Thursday 2pm works for a 10-minute preview!"
      },
      {
        label: 'Lock Q4 Calendar Placeholder',
        intent: 'deferral_lock',
        desc: 'Politely respect timing and secure a tentative early Q4 check-in',
        suggestedDraft: "Appreciate the candor, Alex! I'll put a tentative note on the calendar for early November when budget planning opens up. If you'd like, I can send a 1-page summary of how teams in your space benchmark their SDR volume so you have it on file. Stay great!"
      },
      {
        label: 'Probe Main Pipeline Bottleneck',
        intent: 'probe_pain',
        desc: 'Ask which part of outbound is causing the most friction today',
        suggestedDraft: "Thanks for being upfront, Alex! Before I let you get back to it — curious, heading into Q4, is lead hygiene or response conversion the bigger friction point for your SDRs right now?"
      }
    ],
    simulatedProspectFollowUp: {
      message_text: "Appreciate the practical approach! A free data benchmark with zero budget commitment sounds completely fair. Let's do Thursday at 2:00 PM EST. Send the invite over.",
      resultingOutcome: 'MEETING_BOOKED',
      celebrationText: 'Objection resolved: Alex accepted the free benchmark and agreed to meet Thursday at 2:00 PM.'
    }
  },
  {
    id: 'scenario-competitor-eval',
    threadKey: 'sim-sarah-lin',
    senderName: 'Sarah Lin',
    title: 'Head of Growth',
    company: 'DataPulse FinTech',
    campaignName: 'FinTech Growth Leaders Outreach',
    avatarInitials: 'SL',
    avatarColor: 'bg-muted text-foreground border border-border',
    badge: 'Competitor Compare',
    badgeClass: 'bg-muted text-foreground border-border font-medium',
    objectionType: 'competitor',
    initialOutcome: 'INTERESTED',
    funding: 'Series A ($12M)',
    headcount: '42 Employees',
    techStack: ['HubSpot', 'Lemlist'],
    dealValue: '$14k ARR',
    linkedInUrl: 'https://linkedin.com/in/sarah-lin-growth',
    strategyRationale: 'Actively comparing Lemlist and Expandi. Pivot to 4G dedicated residential proxy isolation and direct HubSpot sync.',
    messages: [
      {
        id: 'sim-msg-3',
        sender_name: 'You',
        message_text: "Sarah, loved your recent article on account-based outbound efficiency. Quick question - are your growth reps still manually logging LinkedIn acceptance rates into your CRM?",
        direction: 'outbound',
        created_at: new Date(Date.now() - 2 * 86400000).toISOString()
      },
      {
        id: 'sim-msg-4',
        sender_name: 'Sarah Lin',
        message_text: "We're actually evaluating Lemlist and Expandi right now. The biggest headache for us is LinkedIn account safety and pushing status changes directly into HubSpot deals. How does Ele-in prevent account bans, and do you sync bi-directionally with HubSpot?",
        direction: 'inbound',
        created_at: new Date(Date.now() - 7200000).toISOString()
      }
    ],
    intentChips: [
      {
        label: 'Residential 4G Proxy Isolation',
        intent: 'proxy_safety',
        desc: 'Highlight dedicated residential IPs vs dangerous shared datacenter IPs',
        suggestedDraft: "Spot-on question, Sarah. The fundamental difference: Lemlist and Expandi route through shared datacenter IP pools that trigger LinkedIn's automated checkpoints. Ele-in assigns dedicated residential 4G proxies with human behavioral jitter - LinkedIn sees genuine mobile/residential browser sessions. Plus, our bi-directional HubSpot sync pushes sentiment tags and meeting status straight into your deals. Would a 3-minute video walkthrough help?"
      },
      {
        label: 'Real-Time HubSpot Sync',
        intent: 'hubspot_sync',
        desc: 'Detail stage tracking, contact enrichment, and deal sync',
        suggestedDraft: "Yes, 100% native! Ele-in auto-creates or updates HubSpot contacts, logs conversation transcripts, and advances deal stages the second a prospect replies. No Zapier required. Happy to show you the live sync in a 10-minute demo tomorrow afternoon!"
      },
      {
        label: '15-Min Architecture Walkthrough',
        intent: 'book_demo',
        desc: 'Suggest 2 concrete times for a comparative demonstration',
        suggestedDraft: "Would love to walk you through the side-by-side architecture with Expandi and demonstrate the HubSpot sync live. Are you free tomorrow at 3:00 PM or Thursday at 11:00 AM?"
      }
    ],
    simulatedProspectFollowUp: {
      message_text: "That residential proxy setup is exactly what we need - we had two SDR profiles temporarily restricted last quarter on shared IPs. Let's do tomorrow at 3:00 PM. Here's my direct email: sarah@datapulse.io.",
      resultingOutcome: 'MEETING_BOOKED',
      celebrationText: 'Competitive win: Sarah confirmed dedicated residential proxy safety was her deciding factor.'
    }
  },
  {
    id: 'scenario-authenticity-check',
    threadKey: 'sim-marcus-vance',
    senderName: 'Marcus Vance',
    title: 'Co-Founder & CTO',
    company: 'StealthAI',
    campaignName: 'AI Founders Direct Sequence',
    avatarInitials: 'MV',
    avatarColor: 'bg-muted text-foreground border border-border',
    badge: 'Authenticity Check',
    badgeClass: 'bg-muted text-foreground border-border font-medium',
    objectionType: 'authenticity',
    initialOutcome: 'FOLLOW_UP',
    funding: 'Seed ($3.2M)',
    headcount: '18 Employees',
    techStack: ['Linear', 'Apollo'],
    dealValue: '$9.6k ARR',
    linkedInUrl: 'https://linkedin.com/in/marcus-vance-ai',
    strategyRationale: 'Skeptical of robotic bot outreach. Respond with human-engineer authenticity, referencing his open-source work.',
    messages: [
      {
        id: 'sim-msg-5',
        sender_name: 'You',
        message_text: "Marcus, saw your open-source release on agentic task loops — brilliant architecture. We're working with AI founders who want to test market demand without spending 3 hours a day sending manual DMs.",
        direction: 'outbound',
        created_at: new Date(Date.now() - 4 * 86400000).toISOString()
      },
      {
        id: 'sim-msg-6',
        sender_name: 'Marcus Vance',
        message_text: "Curious how you came across our repo. Usually get bombarded by offshore lead agencies with fake profiles. Is this an automated sequence or are you a real person?",
        direction: 'inbound',
        created_at: new Date(Date.now() - 1800000).toISOString()
      }
    ],
    intentChips: [
      {
        label: 'Founder Transparency',
        intent: 'human_founder',
        desc: 'Genuine founder response explaining why you reached out',
        suggestedDraft: "100% real human on this side, Marcus! I was researching teams building open-source LLM agent harnesses on GitHub and came across your recent commits on autonomous execution loops. We built Ele-in specifically because we despise robotic spam bots. We believe outbound should feel like an authentic dialogue between builders. Would love to compare notes over a casual virtual coffee if you're open!"
      },
      {
        label: 'Technical Architecture Reference',
        intent: 'tech_deepdive',
        desc: 'Discuss agentic task execution and engineering parallels',
        suggestedDraft: "Guilty of being a real engineer! Specifically loved how your loop handles state recovery without infinite retries. We solve a similar problem with residential session state. Happy to swap notes if you're ever curious!"
      },
      {
        label: 'Virtual Coffee / Casual Chat',
        intent: 'casual_chat',
        desc: 'Low-pressure invite to compare notes without sales pitch',
        suggestedDraft: "Real person here! No sales pitch — just genuinely impressed by the project. Would love to grab 10 minutes this Friday morning to talk agent frameworks if you have a break in your schedule."
      }
    ],
    simulatedProspectFollowUp: {
      message_text: "Haha, respect for the genuine response! Too many generic bots out there. Friday at 10:30 AM works for a quick virtual coffee. Ping me the link.",
      resultingOutcome: 'INTERESTED',
      celebrationText: 'Connection confirmed: Marcus verified your authenticity and agreed to connect Friday.'
    }
  }
];
