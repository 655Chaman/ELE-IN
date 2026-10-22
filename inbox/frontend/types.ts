import { Calendar, Clock, FileText, Target, XCircle } from 'lucide-react';

export type DealStage = 
  | 'NEW_REPLY' 
  | 'OBJECTION_RAISED' 
  | 'BATTLECARD_ENGAGED' 
  | 'MEETING_PROPOSED' 
  | 'MEETING_CONFIRMED' 
  | 'CLOSED_WON' 
  | 'DISQUALIFIED';

export interface ObjectionData {
  objection_type: string;
  confidence: number;
  detected_competitor?: string;
  competitor_intel?: {
    competitor: string;
    strengths_acknowledged?: string;
    kill_points?: string[];
    pivot_angle?: string;
  };
  detected_timing?: string;
  detected_referral?: string;
  summary?: string;
}

export interface ThreadSummary {
  sender_name: string;
  lead_id?: string;
  account_id?: string;
  thread_key: string;
  last_message: string;
  direction: string;
  created_at: string;
  type?: string;
  unread_count?: number;
  deal_stage?: DealStage;
  objection_data?: ObjectionData | null;
  lead_timezone?: string;
  intent?: string;
  company?: string;
  title?: string;
  campaign_id?: string;
  campaign_name?: string;
}

export interface DealStageConfig {
  id: DealStage;
  label: string;
  badgeClass: string;
  pillActiveClass: string;
  description: string;
}

export const DEAL_STAGES: Record<DealStage, DealStageConfig> = {
  NEW_REPLY: {
    id: 'NEW_REPLY',
    label: 'New Reply',
    badgeClass: 'bg-muted text-foreground border-border',
    pillActiveClass: 'bg-primary/10 text-primary border-primary/30 font-medium',
    description: 'Fresh inbound prospect response received'
  },
  OBJECTION_RAISED: {
    id: 'OBJECTION_RAISED',
    label: 'Objection Raised',
    badgeClass: 'bg-warning/10 text-warning border-warning/20',
    pillActiveClass: 'bg-warning/15 text-warning border-warning/30 font-medium',
    description: 'Competitor, budget, or timing pushback detected'
  },
  BATTLECARD_ENGAGED: {
    id: 'BATTLECARD_ENGAGED',
    label: 'Battlecard Deployed',
    badgeClass: 'bg-primary/10 text-primary border-primary/20',
    pillActiveClass: 'bg-primary/15 text-primary border-primary/30 font-medium',
    description: 'Tailored counter-pitch sent to reframe conversation'
  },
  MEETING_PROPOSED: {
    id: 'MEETING_PROPOSED',
    label: 'Meeting Proposed',
    badgeClass: 'bg-primary/10 text-primary border-primary/20',
    pillActiveClass: 'bg-primary/15 text-primary border-primary/30 font-medium',
    description: 'Specific localized calendar slots offered'
  },
  MEETING_CONFIRMED: {
    id: 'MEETING_CONFIRMED',
    label: 'Meeting Confirmed',
    badgeClass: 'bg-primary text-primary-foreground border-primary font-medium',
    pillActiveClass: 'bg-primary text-primary-foreground border-primary font-semibold shadow-xs',
    description: 'Call successfully booked on calendar'
  },
  CLOSED_WON: {
    id: 'CLOSED_WON',
    label: 'Closed Won',
    badgeClass: 'bg-primary text-primary-foreground border-primary font-semibold',
    pillActiveClass: 'bg-primary text-primary-foreground border-primary font-semibold shadow-xs',
    description: 'Deal converted into customer'
  },
  DISQUALIFIED: {
    id: 'DISQUALIFIED',
    label: 'Disqualified',
    badgeClass: 'bg-muted text-muted-foreground border-border',
    pillActiveClass: 'bg-muted text-muted-foreground border-border',
    description: 'Unqualified prospect or negative exit'
  }
};

export interface Message {
  id: string;
  message_text: string;
  direction: string;
  created_at: string;
  type?: string;
}

export type OutcomeType = 'INTERESTED' | 'MEETING_BOOKED' | 'FOLLOW_UP' | 'INFO_SENT' | 'NOT_INTERESTED';

export interface OutcomeConfig {
  id: OutcomeType;
  label: string;
  icon: any;
  badgeClass: string;
  pillActiveClass: string;
}

export const OUTCOMES: Record<OutcomeType, OutcomeConfig> = {
  INTERESTED: {
    id: 'INTERESTED',
    label: 'Interested',
    icon: Target,
    badgeClass: 'bg-primary/10 text-primary border-primary/20',
    pillActiveClass: 'bg-primary/15 text-primary border-primary/30 shadow-xs'
  },
  MEETING_BOOKED: {
    id: 'MEETING_BOOKED',
    label: 'Meeting Booked',
    icon: Calendar,
    badgeClass: 'bg-primary text-primary-foreground border-primary font-medium',
    pillActiveClass: 'bg-primary text-primary-foreground border-primary shadow-xs'
  },
  FOLLOW_UP: {
    id: 'FOLLOW_UP',
    label: 'Follow Up',
    icon: Clock,
    badgeClass: 'bg-warning/10 text-warning border-warning/20',
    pillActiveClass: 'bg-warning/15 text-warning border-warning/30 shadow-xs'
  },
  INFO_SENT: {
    id: 'INFO_SENT',
    label: 'Info Sent',
    icon: FileText,
    badgeClass: 'bg-muted text-foreground border-border',
    pillActiveClass: 'bg-muted text-foreground border-border shadow-xs'
  },
  NOT_INTERESTED: {
    id: 'NOT_INTERESTED',
    label: 'Not Interested',
    icon: XCircle,
    badgeClass: 'bg-muted text-muted-foreground border-border',
    pillActiveClass: 'bg-muted text-muted-foreground border-border'
  }
};

export const QUICK_STARTERS = [
  { 
    label: "Book 15-Min Call", 
    text: "Thanks for connecting! I'd love to compare notes on this — do you have 15 minutes open this Thursday or Friday for a quick chat?" 
  },
  { 
    label: "Share Case Study", 
    text: "Great to hear from you! We recently helped a team in your space solve this exact bottleneck. Would you like me to send over the 2-page brief?" 
  },
  { 
    label: "Direct Question", 
    text: "Appreciate the response! Curious — what is your team's current focus for this quarter when it comes to outbound pipeline?" 
  },
  { 
    label: "Gentle Deferral", 
    text: "Appreciate the response! Totally understand if timing is tight right now. Should I touch base again next month when things open up?" 
  }
];

export const AI_INTENT_CHIPS = [
  { label: "Book Call", intent: "positive", desc: "Suggest 2 specific calendar times" },
  { label: "Pushback", intent: "objection", desc: "Empathize & pivot to differentiator" },
  { label: "Answer & Bridge", intent: "question", desc: "Answer specifically & bridge forward" },
  { label: "Polite Exit", intent: "negative", desc: "Gracious, zero-pressure door open" },
  { label: "Smart Draft", intent: "unknown", desc: "Warm human contextual follow-up" }
];
