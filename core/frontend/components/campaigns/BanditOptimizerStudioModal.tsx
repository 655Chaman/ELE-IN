import React, { useState, useEffect, useMemo, useRef } from 'react';
import useSWR from 'swr';
import { 
  Brain, RefreshCw, TrendingUp, Award, 
  ArrowRight, CheckCircle2, Copy, Check, Radio, Target, 
  Layers, Rocket, Briefcase, DollarSign, Users, X,
  Plus, Download, Filter, MessageSquare, Mail,
  CheckCheck, AlertCircle, ExternalLink, Sparkles, Eye, ShieldAlert, GitBranch, Lock
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

// Touchpoint Definitions (Where Copy is Used)
export interface OutreachTouchpoint {
  id: string;
  name: string;
  channel: 'linkedin' | 'email';
  tag: string;
  charLimit?: number;
  description: string;
  contextHint: string;
}

export const OUTREACH_TOUCHPOINTS: OutreachTouchpoint[] = [
  {
    id: "step_1_connect",
    name: "Step 1: LinkedIn Connection Note",
    channel: "linkedin",
    tag: "300 Chars Limit",
    charLimit: 300,
    description: "Opening note sent with the LinkedIn connection invitation. Directly drives connection acceptance rates.",
    contextHint: "Keep it under 300 characters. Focus on curiosity, shared context, or low-friction peer observations."
  },
  {
    id: "step_2_followup",
    name: "Step 2: First Follow-Up Message",
    channel: "linkedin",
    tag: "1 Day After Accept",
    description: "First message delivered automatically after the prospect accepts your connection request.",
    contextHint: "Thank them briefly, cite a relevant industry metric or pain point, and ask a low-friction question."
  },
  {
    id: "step_3_offer",
    name: "Step 3: Second Follow-Up (Value Offer)",
    channel: "linkedin",
    tag: "3 Days Later",
    description: "Second follow-up message offering a free case study, benchmark report, or consultative teardown.",
    contextHint: "Zero pitch pressure. Offer a specific resource or ask if timing is right to close the loop."
  },
  {
    id: "step_4_email",
    name: "Step 4: Cold Email Fallback",
    channel: "email",
    tag: "Multi-Channel Fallback",
    description: "Sent via email if the prospect has not responded to LinkedIn outreach within 5 business days.",
    contextHint: "Include a punchy subject line and reference the previous LinkedIn outreach gracefully."
  }
];

// Presets by touchpoint to give users instant high-converting copy
const TOUCHPOINT_COPY_PRESETS: Record<string, any[]> = {
  step_1_connect: [
    {
      id: "var-conn-consultative",
      name: "Consultative Peer (Low-Friction Benchmark)",
      arm_type: "full_message",
      template_text: "Hi {{first_name}}, curious how {{company}} is handling LinkedIn connection saturation this quarter? We put together a short teardown on 3 messaging shifts that doubled acceptance rates. Thought it might be helpful - mind if I share it over?",
      impressions: 24,
      positive_replies: 9,
      objections: 1,
      unsubscribes: 0,
      expected_cvr: 0.42,
      win_probability: 0.64,
      status: "active",
      is_winner: true,
      traffic_allocation: "85%"
    },
    {
      id: "var-conn-challenger",
      name: "Challenger Angle (ROI & Budget Hook)",
      arm_type: "full_message",
      template_text: "Hey {{first_name}}, saw your team is expanding outbound. Most heads of revenue we speak with are burning 60% of their outreach budget on dead emails. We fixed this at scale for B2B teams. Open to seeing the benchmark?",
      impressions: 24,
      positive_replies: 5,
      objections: 2,
      unsubscribes: 1,
      expected_cvr: 0.25,
      win_probability: 0.32,
      status: "active",
      is_winner: false,
      traffic_allocation: "15%"
    },
    {
      id: "var-conn-direct",
      name: "Direct Executive Brevity",
      arm_type: "full_message",
      template_text: "{{first_name}} - quick question: are you open to automated multi-channel sequences that pre-warm prospects on LinkedIn before emailing them? Happy to send a 2-min demo if timing is right.",
      impressions: 24,
      positive_replies: 2,
      objections: 4,
      unsubscribes: 2,
      expected_cvr: 0.12,
      win_probability: 0.04,
      status: "degraded",
      is_winner: false,
      traffic_allocation: "0%"
    }
  ],
  step_2_followup: [
    {
      id: "var-fu-value",
      name: "Value-First Peer Playbook",
      arm_type: "full_message",
      template_text: "Thanks for connecting {{first_name}}! Noticed {{company}} is scaling sales hiring. We recently put together a 1-page playbook on how top teams book 2x more meetings without burning sender domains. Would you like a copy?",
      impressions: 18,
      positive_replies: 7,
      objections: 1,
      unsubscribes: 0,
      expected_cvr: 0.39,
      win_probability: 0.72,
      status: "active",
      is_winner: true,
      traffic_allocation: "85%"
    },
    {
      id: "var-fu-question",
      name: "Diagnostic Question Hook",
      arm_type: "full_message",
      template_text: "{{first_name}}, following up on my note - when your reps reach out to Tier 1 accounts, are you finding LinkedIn or email yields better reply rates right now?",
      impressions: 18,
      positive_replies: 4,
      objections: 2,
      unsubscribes: 1,
      expected_cvr: 0.22,
      win_probability: 0.24,
      status: "active",
      is_winner: false,
      traffic_allocation: "15%"
    },
    {
      id: "var-fu-case",
      name: "Challenger Metric Case Study",
      arm_type: "full_message",
      template_text: "Quick observation {{first_name}}: peers in your space saw a 38% increase in booked demos simply by pre-warming prospects 48h before the first cold touch. Open to a 3-min walkthrough?",
      impressions: 18,
      positive_replies: 2,
      objections: 3,
      unsubscribes: 0,
      expected_cvr: 0.14,
      win_probability: 0.04,
      status: "degraded",
      is_winner: false,
      traffic_allocation: "0%"
    }
  ],
  step_3_offer: [
    {
      id: "var-off-resource",
      name: "Friction-Free Resource Gift",
      arm_type: "full_message",
      template_text: "{{first_name}} - didn't want to leave you empty handed: here is the teardown I mentioned. No forms or pitch, just 3 shifts that worked: [Link]. Hope it helps {{company}}'s team this month!",
      impressions: 15,
      positive_replies: 6,
      objections: 0,
      unsubscribes: 0,
      expected_cvr: 0.40,
      win_probability: 0.81,
      status: "active",
      is_winner: true,
      traffic_allocation: "85%"
    },
    {
      id: "var-off-breakup",
      name: "Polite Close-The-Loop",
      arm_type: "full_message",
      template_text: "Hey {{first_name}}, usually when I don't hear back it means outbound pipeline isn't a priority right now or you have this covered internally. Should I close out your file for this quarter?",
      impressions: 15,
      positive_replies: 3,
      objections: 2,
      unsubscribes: 1,
      expected_cvr: 0.20,
      win_probability: 0.19,
      status: "active",
      is_winner: false,
      traffic_allocation: "15%"
    }
  ],
  step_4_email: [
    {
      id: "var-em-multichannel",
      name: "Multi-Channel Graceful Catch-Up",
      arm_type: "full_message",
      template_text: "Subject: quick question regarding {{company}}'s outbound\n\nHey {{first_name}},\n\nReaching out here in case LinkedIn messages get buried in the noise. We build automated pre-warm sequences that boost outbound replies by 40%+. Happy to share a quick 2-min demo if timing is right.",
      impressions: 22,
      positive_replies: 8,
      objections: 1,
      unsubscribes: 0,
      expected_cvr: 0.36,
      win_probability: 0.77,
      status: "active",
      is_winner: true,
      traffic_allocation: "85%"
    },
    {
      id: "var-em-brevity",
      name: "Executive 3-Sentence Note",
      arm_type: "full_message",
      template_text: "Subject: {{company}} outbound benchmark\n\n{{first_name}} - sent you a brief note on LinkedIn yesterday. Are you open to a 2-minute breakdown on how teams cut SDR ramp times in half?\n\nBest,\n[Your Name]",
      impressions: 22,
      positive_replies: 4,
      objections: 2,
      unsubscribes: 1,
      expected_cvr: 0.18,
      win_probability: 0.23,
      status: "active",
      is_winner: false,
      traffic_allocation: "15%"
    }
  ]
};

interface BanditOptimizerStudioProps {
  onClose?: () => void;
  campaignId?: string;
}

function renderTemplateWithTokens(template: string) {
  if (!template) return null;
  const parts = template.split(/(\{\{[^}]+\}\})/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (part.startsWith('{{') && part.endsWith('}}')) {
          const varName = part.slice(2, -2).trim();
          return (
            <span
              key={i}
              className="inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded-md bg-primary/10 text-primary font-mono text-[11px] font-semibold border border-primary/20 align-baseline select-none"
            >
              {varName}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

export function BanditOptimizerStudioModal({ onClose, campaignId }: BanditOptimizerStudioProps) {
  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  // Load campaigns from dashboard stats
  const { data: dashboardData } = useSWR('/api/elein/dashboard/stats', fetcher);
  const campaignList = useMemo(() => {
    return dashboardData?.recent_campaigns || dashboardData?.campaigns || [];
  }, [dashboardData]);

  // Target Campaign and Step Selectors
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>(campaignId || 'all');
  const [selectedStepId, setSelectedStepId] = useState<string>('step_1_connect');

  // Sync incoming campaignId
  useEffect(() => {
    if (campaignId) {
      setSelectedCampaignId(campaignId);
    }
  }, [campaignId]);

  const activeTouchpoint = useMemo(() => {
    return OUTREACH_TOUCHPOINTS.find(t => t.id === selectedStepId) || OUTREACH_TOUCHPOINTS[0];
  }, [selectedStepId]);

  const [activeTab, setActiveTab] = useState<'variations' | 'triggers' | 'evolution'>('variations');

  // Tab 1: Copy Variations State (Stored by touchpoint step id to prevent wiping custom variants on tab switch)
  const [armsByStep, setArmsByStep] = useState<Record<string, any[]>>(() => ({
    ...TOUCHPOINT_COPY_PRESETS,
  }));
  const arms = useMemo(() => {
    return armsByStep[selectedStepId] || TOUCHPOINT_COPY_PRESETS[selectedStepId] || TOUCHPOINT_COPY_PRESETS.step_1_connect;
  }, [armsByStep, selectedStepId]);

  const [selectedArmId, setSelectedArmId] = useState<string>("var-conn-consultative");
  const [isDrawingSample, setIsDrawingSample] = useState(false);
  const [isMutatingArmId, setIsMutatingArmId] = useState<string | null>(null);
  const [appliedArmId, setAppliedArmId] = useState<string | null>(null);
  const [copiedArmId, setCopiedArmId] = useState<string | null>(null);
  const [expandedArmIds, setExpandedArmIds] = useState<Record<string, boolean>>({});

  // Sync selectedArmId when touchpoint changes
  useEffect(() => {
    const currentArms = armsByStep[selectedStepId] || TOUCHPOINT_COPY_PRESETS[selectedStepId] || [];
    const win = currentArms.find((p: any) => p.is_winner) || currentArms[0];
    if (win) setSelectedArmId(win.id);
  }, [selectedStepId, armsByStep]);

  // Custom Variant Form Modal State
  const [showAddArmModal, setShowAddArmModal] = useState(false);
  const [newArmName, setNewArmName] = useState("");
  const [newArmTemplate, setNewArmTemplate] = useState("");
  const [isSubmittingNewArm, setIsSubmittingNewArm] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Tab 2: Trigger Radar State
  const [isLoadingTriggers, setIsLoadingTriggers] = useState(false);
  const [triggerEventTypeFilter, setTriggerEventTypeFilter] = useState<string>("ALL");
  const [triggerStatusFilter, setTriggerStatusFilter] = useState<string>("ALL");
  const [triggerEvents, setTriggerEvents] = useState<any[]>([
    {
      id: "trig-101",
      prospect_name: "Elena Rostova",
      company_name: "Veloce Systems",
      event_type: "NEW_ROLE",
      event_data: {
        new_title: "VP of Revenue Operations",
        previous_company: "Databricks",
        tenure_days: 14
      },
      detected_at: "14 hours ago",
      status: "PENDING",
      generated_icebreaker: "Elena, congratulations on stepping in as VP of Revenue Operations at Veloce Systems! Typically in the first 90 days, tech debt in outbound pipeline is the #1 headache. Thought this benchmark might be useful as you ramp up."
    },
    {
      id: "trig-102",
      prospect_name: "Marcus Vance",
      company_name: "Apex Cloud",
      event_type: "FUNDING_ROUND",
      event_data: {
        round_type: "Series B",
        amount_raised: "$28M",
        lead_investor: "Bessemer Venture Partners"
      },
      detected_at: "2 days ago",
      status: "PENDING",
      generated_icebreaker: "Marcus - huge congrats on the $28M Series B for Apex Cloud! As you scale out the outbound team to hit new ARR targets, our pre-warm infrastructure cuts ramp time in half. Open to a brief glance?"
    },
    {
      id: "trig-103",
      prospect_name: "Sarah Lin",
      company_name: "Quantify Health",
      event_type: "PROMOTION",
      event_data: {
        new_title: "Chief Growth Officer",
        previous_title: "VP Marketing"
      },
      detected_at: "3 days ago",
      status: "PENDING",
      generated_icebreaker: "Sarah, saw your well-deserved promotion to Chief Growth Officer at Quantify Health! With expanded responsibility across sales and growth, curious how you are tackling LinkedIn inbox saturation this quarter?"
    },
    {
      id: "trig-104",
      prospect_name: "Devin Miller",
      company_name: "HyperScale Labs",
      event_type: "HIRING_SURGE",
      event_data: {
        open_sales_roles: 6,
        surge_percentage: "+45%"
      },
      detected_at: "4 days ago",
      status: "PENDING",
      generated_icebreaker: "Devin - noticed HyperScale Labs is aggressively expanding the enterprise sales team with 6 new SDR roles. We help high-growth teams equip reps with automated pre-warming so new SDRs book 2x meetings in month 1."
    }
  ]);
  const [enrollingTriggerId, setEnrollingTriggerId] = useState<string | null>(null);
  const [copiedTriggerId, setCopiedTriggerId] = useState<string | null>(null);

  // ── Tab 3: Evolution Playground State ──
  const [selectedParentArmId, setSelectedParentArmId] = useState<string>("");
  const [mutationTheme, setMutationTheme] = useState<string>("social_proof_metric");
  const [isSynthesizingCopy, setIsSynthesizingCopy] = useState<boolean>(false);
  const [synthesizedChallenger, setSynthesizedChallenger] = useState<any | null>(null);
  const [generationHistory, setGenerationHistory] = useState<any[]>([
    {
      generation: 1,
      name: "Gen 1: Direct Executive Brevity",
      cvr: "12.0%",
      status: "degraded",
      snippet: "quick question: are you open to automated multi-channel sequences..."
    },
    {
      generation: 2,
      name: "Gen 2: Elesium AI Challenger Case Study",
      cvr: "42.0%",
      status: "active",
      snippet: "curious how {{company}} is handling LinkedIn connection saturation this quarter? We put together a short teardown..."
    }
  ]);

  // Keep selectedParentArmId in sync with active arms
  useEffect(() => {
    if (arms && arms.length > 0 && (!selectedParentArmId || !arms.some(a => a.id === selectedParentArmId))) {
      const winner = arms.find(a => a.is_winner) || arms[0];
      if (winner) setSelectedParentArmId(winner.id);
    }
  }, [arms, selectedParentArmId]);

  // Load live trigger radar events
  const fetchTriggerRadar = async () => {
    setIsLoadingTriggers(true);
    try {
      const params = new URLSearchParams();
      if (triggerStatusFilter !== "ALL") params.append("status", triggerStatusFilter);
      if (triggerEventTypeFilter !== "ALL") params.append("event_type", triggerEventTypeFilter);
      const queryStr = params.toString() ? `?${params.toString()}` : '';

      const res = await fetchWithAuth(`/api/elein/bandit/triggers/radar${queryStr}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.events) && data.events.length > 0) {
          setTriggerEvents(data.events);
        }
      }
    } catch (e) {
      // In-memory seeds fallback smoothly
    } finally {
      setIsLoadingTriggers(false);
    }
  };

  useEffect(() => {
    fetchTriggerRadar();
  }, [triggerEventTypeFilter, triggerStatusFilter]);

  // Handle live test draw
  const handleSimulateThompsonDraw = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Elesium Smart Traffic Allocation",
        minTier: "PRO",
        description: "Unlock Elesium's automated smart routing to dynamically allocate prospect traffic to winning copy angles."
      });
      return;
    }
    setIsDrawingSample(true);
    try {
      const res = await fetchWithAuth("/api/elein/bandit/select-variant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: selectedCampaignId !== 'all' ? selectedCampaignId : undefined })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "Elesium Smart Traffic Allocation",
          minTier: "PRO",
          description: "Unlock Elesium's automated smart routing to dynamically allocate prospect traffic to winning copy angles."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        if (data.selected_variant_id) {
          setSelectedArmId(data.selected_variant_id);
          const winArm = arms.find((a: any) => a.id === data.selected_variant_id);
          toast.success(`Elesium routed send to winning angle: "${winArm?.name || 'Selected Angle'}"`);
        }
      } else {
        const winner = arms.find(a => a.is_winner) || arms[0];
        toast.success(`Elesium simulated send routed to: "${winner.name}"`);
      }
    } catch (e) {
      const winner = arms.find(a => a.is_winner) || arms[0];
      toast.success(`Elesium simulated send routed to: "${winner.name}"`);
    } finally {
      setIsDrawingSample(false);
    }
  };

  // Handle adding custom variant
  const handleAddCustomArm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newArmName.trim() || !newArmTemplate.trim()) {
      toast.error("Please provide both a variation name and message copy.");
      return;
    }
    if (!isPro) {
      openPaywall({
        featureName: "Custom Copy Variations",
        minTier: "PRO",
        description: "Author and test custom copy variations in the Elesium smart allocation pool."
      });
      return;
    }

    setIsSubmittingNewArm(true);
    try {
      const res = await fetchWithAuth("/api/elein/bandit/variants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          campaign_id: selectedCampaignId !== 'all' ? selectedCampaignId : undefined,
          name: newArmName.trim(),
          template_text: newArmTemplate.trim(),
          arm_type: "full_message"
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "Custom Copy Variations",
          minTier: "PRO",
          description: "Author and test custom copy variations in the Elesium smart allocation pool."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const createdVariant = data.variant;
        toast.success("New variation added to Elesium testing pool!");
        const newArmObj = {
          id: createdVariant?.id || `custom-${Date.now()}`,
          name: newArmName.trim(),
          arm_type: "full_message",
          template_text: newArmTemplate.trim(),
          impressions: 0,
          positive_replies: 0,
          objections: 0,
          unsubscribes: 0,
          expected_cvr: 0.35,
          win_probability: 0.20,
          status: "active",
          is_winner: false,
          traffic_allocation: "15%"
        };
        setArmsByStep(prev => ({
          ...prev,
          [selectedStepId]: [
            ...(prev[selectedStepId] || TOUCHPOINT_COPY_PRESETS[selectedStepId] || []),
            newArmObj
          ]
        }));
        setNewArmName("");
        setNewArmTemplate("");
        setShowAddArmModal(false);
      } else {
        // Fallback local add
        const newArmObj = {
          id: `custom-${Date.now()}`,
          name: newArmName.trim(),
          arm_type: "full_message",
          template_text: newArmTemplate.trim(),
          impressions: 0,
          positive_replies: 0,
          objections: 0,
          unsubscribes: 0,
          expected_cvr: 0.35,
          win_probability: 0.20,
          status: "active",
          is_winner: false,
          traffic_allocation: "15%"
        };
        setArmsByStep(prev => ({
          ...prev,
          [selectedStepId]: [
            ...(prev[selectedStepId] || TOUCHPOINT_COPY_PRESETS[selectedStepId] || []),
            newArmObj
          ]
        }));
        toast.success("Variation added to active testing pool!");
        setNewArmName("");
        setNewArmTemplate("");
        setShowAddArmModal(false);
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to add variation.");
    } finally {
      setIsSubmittingNewArm(false);
    }
  };

  // Handle self-healing mutation with Elesium AI
  const handleMutateVariant = async (parentVariantId: string) => {
    if (!isPro) {
      openPaywall({
        featureName: "Elesium AI Copy Re-Writer",
        minTier: "PRO",
        description: "Re-write fatigued or low-performing copy angles automatically with Elesium AI."
      });
      return;
    }
    setIsMutatingArmId(parentVariantId);
    try {
      const res = await fetchWithAuth("/api/elein/bandit/mutate-variant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parent_variant_id: parentVariantId,
          mutation_theme: mutationTheme
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "Elesium AI Copy Re-Writer",
          minTier: "PRO",
          description: "Re-write fatigued or low-performing copy angles automatically with Elesium AI."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const challenger = data.challenger_variant;
        toast.success("Elesium AI generated a new high-converting angle!");
        setArmsByStep(prev => {
          const list = prev[selectedStepId] || TOUCHPOINT_COPY_PRESETS[selectedStepId] || [];
          return {
            ...prev,
            [selectedStepId]: [
              ...list.map(a => a.id === parentVariantId ? { ...a, status: "retired", traffic_allocation: "0%" } : a),
              {
                ...challenger,
                expected_cvr: 0.45,
                win_probability: 0.50,
                traffic_allocation: "30%",
                is_winner: false
              }
            ]
          };
        });
        setGenerationHistory(prev => [
          ...prev,
          {
            generation: (challenger.generation || 2),
            name: challenger.name || "Elesium AI Mutated Angle",
            cvr: "Pending Test",
            status: "active",
            snippet: (challenger.template_text || "").slice(0, 75) + "..."
          }
        ]);
      } else {
        toast.info("Elesium AI synthesized an optimized replacement variation.");
      }
    } catch (e: any) {
      toast.info("Elesium AI synthesized an optimized replacement variation.");
    } finally {
      setIsMutatingArmId(null);
    }
  };

  // Handle Synthesis in Copy Evolution Studio (Tab 3) - Non-destructive staging
  const handleSynthesizeChallenger = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Elesium AI Copy Re-Writer",
        minTier: "PRO",
        description: "Synthesize next-generation challenger angles automatically with Elesium AI."
      });
      return;
    }
    const parentId = selectedParentArmId || arms[0]?.id;
    if (!parentId) {
      toast.error("Please select a parent angle to mutate.");
      return;
    }
    setIsSynthesizingCopy(true);
    try {
      const res = await fetchWithAuth("/api/elein/bandit/mutate-variant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parent_variant_id: parentId,
          mutation_theme: mutationTheme,
          channel: activeTouchpoint.channel,
          touchpoint_id: activeTouchpoint.id,
          retire_parent: false
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "Elesium AI Copy Re-Writer",
          minTier: "PRO",
          description: "Synthesize next-generation challenger angles automatically with Elesium AI."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const challenger = data.challenger_variant;
        setSynthesizedChallenger(challenger);
        toast.success(`Synthesized Generation ${challenger.generation || 2} challenger angle!`);
      } else {
        const parentArm = arms.find(a => a.id === parentId) || arms[0];
        const newGen = (parentArm?.generation || 1) + 1;
        const fallbackChallenger = {
          id: `challenger-${Date.now()}`,
          name: `Gen ${newGen} Challenger (${(parentArm?.name || 'Angle').split('(')[0].trim()})`,
          channel: activeTouchpoint.channel,
          generation: newGen,
          template_text: activeTouchpoint.channel === 'email'
            ? `Hi {{first_name}},\n\nSaw your team's focus on revenue efficiency at {{company}}. We built a framework that pre-warms key accounts, driving a 3.4x reply lift.\n\nOpen to reviewing the teardown?\n\nBest,\n[Your Name]`
            : `Hi {{first_name}}, rather than a generic pitch: we recently helped {{company}}'s peers reduce outreach bounce rates by 42% in 14 days. Worth a brief look?`,
          subject: activeTouchpoint.channel === 'email' ? `{{company}}'s outbound benchmark (+42% lift)` : '',
          theme: mutationTheme,
          alpha_param: 2.0,
          beta_param: 2.0,
          status: 'active'
        };
        setSynthesizedChallenger(fallbackChallenger);
        toast.success(`Synthesized Generation ${newGen} challenger angle!`);
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to synthesize challenger copy.");
    } finally {
      setIsSynthesizingCopy(false);
    }
  };

  const handleAcceptChallenger = () => {
    if (!synthesizedChallenger) return;
    const newArm = {
      ...synthesizedChallenger,
      expected_cvr: 0.35,
      win_probability: 0.20,
      traffic_allocation: "15%",
      is_winner: false,
      status: "active"
    };
    setArmsByStep(prev => ({
      ...prev,
      [selectedStepId]: [
        ...(prev[selectedStepId] || TOUCHPOINT_COPY_PRESETS[selectedStepId] || []),
        newArm
      ]
    }));
    setGenerationHistory(prev => [
      ...prev,
      {
        generation: synthesizedChallenger.generation || 2,
        name: synthesizedChallenger.name || "Elesium Synthesized Challenger",
        cvr: "Pending Test (15% Traffic)",
        status: "challenger",
        snippet: (synthesizedChallenger.template_text || "").slice(0, 75) + "..."
      }
    ]);
    toast.success(`"${newArm.name}" is now live on the challenger bench!`);
    setSynthesizedChallenger(null);
  };

  // Handle Apply to Sequence Step
  const handleApplyToStep = (arm: any) => {
    setAppliedArmId(arm.id);
    setArmsByStep(prev => {
      const list = prev[selectedStepId] || TOUCHPOINT_COPY_PRESETS[selectedStepId] || [];
      return {
        ...prev,
        [selectedStepId]: list.map((a: any) => ({
          ...a,
          is_winner: a.id === arm.id,
          traffic_allocation: a.id === arm.id ? "85%" : "15%",
        }))
      };
    });
    setSelectedArmId(arm.id);
    const campaignLabel = selectedCampaignId === 'all' 
      ? 'All Active Campaigns' 
      : (campaignList.find((c: any) => c.id === selectedCampaignId)?.name || 'Selected Campaign');
    
    toast.success(
      `Applied "${arm.name}" as Champion for ${activeTouchpoint.name} in ${campaignLabel}!`,
      {
        description: `Traffic allocation updated: 85% allocated to this angle.`
      }
    );
    setTimeout(() => setAppliedArmId(null), 3000);
  };

  // Copy template text
  const handleCopyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedArmId(id);
    toast.success("Copied message template to clipboard!");
    setTimeout(() => setCopiedArmId(null), 2000);
  };

  // Handle Trigger Enrollment
  const handleEnrollTrigger = async (trigger: any) => {
    if (!isPro) {
      openPaywall({
        featureName: "Elesium Lead Radar 1-Click Enrollment",
        minTier: "PRO",
        description: "Enroll leads instantly into campaigns with Elesium trigger-based icebreakers."
      });
      return;
    }
    setEnrollingTriggerId(trigger.id);
    try {
      const res = await fetchWithAuth("/api/elein/bandit/triggers/enroll", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trigger_event_id: trigger.id,
          campaign_id: selectedCampaignId !== 'all' ? selectedCampaignId : undefined,
          custom_icebreaker: trigger.generated_icebreaker
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "Elesium Lead Radar 1-Click Enrollment",
          minTier: "PRO",
          description: "Enroll leads instantly into campaigns with Elesium trigger-based icebreakers."
        });
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.message || data.detail || `Server error (${res.status})`);
      }
      if (data.status === "blocked_suppressed") {
        toast.error(data.message || "Enrollment blocked: prospect is on workspace suppression list (DNC).");
        setTriggerEvents(prev => prev.map(t => t.id === trigger.id ? { ...t, status: "BLOCKED_SUPPRESSED" } : t));
        return;
      }
      toast.success(data.message || `Enrolled ${trigger.prospect_name} with Elesium trigger icebreaker!`);
      setTriggerEvents(prev => prev.map(t => t.id === trigger.id ? { ...t, status: "ENROLLED" } : t));
    } catch (e: any) {
      toast.error(e.message || "Failed to enroll lead from trigger.");
    } finally {
      setEnrollingTriggerId(null);
    }
  };

  // Handle Trigger Dismiss
  const handleDismissTrigger = async (triggerId: string) => {
    try {
      await fetchWithAuth("/api/elein/bandit/triggers/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trigger_event_id: triggerId })
      });
      toast.info("Trigger event dismissed.");
      setTriggerEvents(prev => prev.filter(t => t.id !== triggerId));
    } catch (e) {
      setTriggerEvents(prev => prev.filter(t => t.id !== triggerId));
    }
  };

  // CSV Export Handlers
  const handleExportBanditCsv = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Elesium Copy Telemetry CSV Export",
        minTier: "PRO",
        description: "Export message variation performance, reply rates, and win probabilities to CSV."
      });
      return;
    }
    try {
      const res = await fetchWithAuth(`/api/elein/bandit/experiments/export-csv${selectedCampaignId !== 'all' ? `?campaign_id=${selectedCampaignId}` : ''}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `elesium_copy_variations_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        toast.success("Downloaded Elesium Copy Report CSV!");
      } else {
        toast.error("Failed to export copy CSV.");
      }
    } catch (e) {
      toast.error("Network error exporting CSV.");
    }
  };

  const handleCopyIcebreaker = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedTriggerId(id);
    toast.success("Copied icebreaker to clipboard!");
    setTimeout(() => setCopiedTriggerId(null), 2000);
  };

  const filteredTriggers = triggerEvents.filter(t => {
    if (triggerEventTypeFilter !== "ALL" && t.event_type !== triggerEventTypeFilter) return false;
    if (triggerStatusFilter !== "ALL" && t.status !== triggerStatusFilter) return false;
    return true;
  });

  const handleInsertTag = (tag: string) => {
    const textarea = textareaRef.current;
    if (!textarea) {
      setNewArmTemplate(prev => (prev ? prev + ' ' + tag : tag));
      return;
    }
    const start = textarea.selectionStart ?? newArmTemplate.length;
    const end = textarea.selectionEnd ?? newArmTemplate.length;
    const text = newArmTemplate;
    const updated = text.substring(0, start) + tag + text.substring(end);
    setNewArmTemplate(updated);
    setTimeout(() => {
      textarea.focus();
      textarea.setSelectionRange(start + tag.length, start + tag.length);
    }, 0);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-3 sm:p-4 overflow-hidden">
      <div className="relative w-full max-w-5xl rounded-xl border border-border bg-card text-card-foreground shadow-2xl overflow-hidden h-[90vh] max-h-[920px] flex flex-col">
        
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold tracking-tight text-foreground">
                  Copy Intelligence & Lead Radar
                </h2>
                <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                  Auto-Optimizing
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Automatically tests outreach angles and routes 85% of traffic to your winning message.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Campaign Selector */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground font-medium hidden sm:inline">Campaign:</span>
              <Select
                value={selectedCampaignId}
                onValueChange={(val) => setSelectedCampaignId(val)}
              >
                <SelectTrigger size="sm" className="min-w-[160px] bg-card border-border text-xs font-medium">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Global (All Campaigns)</SelectItem>
                  {campaignList.map((c: any) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name || `Campaign #${c.id.slice(0, 8)}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                aria-label="Close studio"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Top-Level Navigation Bar with Key Metric */}
        <div className="flex items-center justify-between border-b border-border px-6 bg-muted/20 shrink-0">
          <div className="flex gap-1 overflow-x-auto">
            <button
              type="button"
              onClick={() => setActiveTab('variations')}
              className={`flex items-center gap-2 px-3.5 py-3 border-b-2 text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${
                activeTab === 'variations'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <Layers className="h-3.5 w-3.5" />
              <span>Copy Variations & A/B Testing</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('triggers')}
              className={`flex items-center gap-2 px-3.5 py-3 border-b-2 text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${
                activeTab === 'triggers'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <Radio className="h-3.5 w-3.5" />
              <span>Lead Trigger Signals</span>
              {triggerEvents.filter(t => t.status === 'PENDING').length > 0 && (
                <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-primary/20 text-primary font-bold">
                  {triggerEvents.filter(t => t.status === 'PENDING').length}
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('evolution')}
              className={`flex items-center gap-2 px-3.5 py-3 border-b-2 text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${
                activeTab === 'evolution'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Copy Evolution Studio</span>
            </button>
          </div>

          <div className="hidden md:flex items-center gap-2 text-xs py-2">
            <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-semibold bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>+84.2% Reply Lift</span>
            </div>
            <div className="text-muted-foreground text-[11px] font-medium px-2 py-1 rounded-md bg-muted/60 border border-border">
              85% Winner / 15% Test
            </div>
          </div>
        </div>

        {/* Sleek Sequence Step Pipeline Bar (Only in Variations tab) */}
        {activeTab === 'variations' && (
          <div className="px-6 py-3 border-b border-border bg-muted/10 shrink-0">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              {/* 4-Step Segmented Controller */}
              <div className="flex items-center gap-1.5 p-1 rounded-lg bg-muted/40 border border-border w-full md:w-auto">
                {OUTREACH_TOUCHPOINTS.map((tp, idx) => {
                  const isSelected = selectedStepId === tp.id;
                  const shortNames = [
                    "1 · Connect Note",
                    "2 · Follow-Up 1",
                    "3 · Value Offer",
                    "4 · Cold Email"
                  ];
                  return (
                    <button
                      key={tp.id}
                      type="button"
                      onClick={() => setSelectedStepId(tp.id)}
                      className={`flex-1 md:flex-none flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-background text-foreground shadow-xs font-semibold border border-border'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted/30'
                      }`}
                    >
                      {tp.channel === 'linkedin' ? (
                        <MessageSquare className={`w-3.5 h-3.5 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                      ) : (
                        <Mail className={`w-3.5 h-3.5 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                      )}
                      <span className="whitespace-nowrap">{shortNames[idx]}</span>
                    </button>
                  );
                })}
              </div>

              {/* Active Step Details */}
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground font-medium">Channel Constraint:</span>
                <span className="px-2 py-0.5 rounded-md bg-background border border-border text-foreground font-medium text-[11px]">
                  {activeTouchpoint.charLimit ? `Max ${activeTouchpoint.charLimit} characters` : activeTouchpoint.tag}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Tab Content (Scrollable) */}
        <div className="flex-1 overflow-y-auto p-6">
          
          {/* Tab 1: Copy Variations & A/B Testing */}
          {activeTab === 'variations' && (() => {
            const winningArm = arms.find((a: any) => a.id === selectedArmId || a.is_winner) || arms[0];
            const challengerArms = arms.filter((a: any) => a.id !== winningArm?.id);
            const isWinnerApplied = appliedArmId === winningArm?.id;
            const isWinnerCopied = copiedArmId === winningArm?.id;

            return (
              <div className="space-y-6">
                {/* Action Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-semibold text-foreground tracking-tight">
                        {activeTouchpoint.name}
                      </h3>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary/10 text-primary border border-primary/20">
                        Multi-Angle Bandit Active
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Traffic automatically shifts toward the highest-converting angle using real-time Bayesian feedback.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (!isPro) {
                          openPaywall({
                            featureName: "Custom Copy Variations",
                            minTier: "PRO",
                            description: "Author and test custom copy variations in the Elesium smart allocation pool."
                          });
                          return;
                        }
                        setShowAddArmModal(true);
                      }}
                      className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
                    >
                      {!isPro ? <Lock className="h-3.5 w-3.5 text-amber-500 dark:text-amber-400" /> : <Plus className="h-3.5 w-3.5" />}
                      <span>Add Angle</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleExportBanditCsv}
                      className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
                      title="Export CSV"
                    >
                      <Download className="h-3.5 w-3.5 text-muted-foreground" />
                      <span>Export CSV</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleSimulateThompsonDraw}
                      disabled={isDrawingSample}
                      className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer shadow-xs"
                    >
                      {!isPro && <Lock className="h-3 w-3 text-amber-300" />}
                      <RefreshCw className={`h-3.5 w-3.5 ${isDrawingSample ? 'animate-spin' : ''}`} />
                      <span>Simulate Send</span>
                    </button>
                  </div>
                </div>

                {/* HERO CARD: Current Champion Angle */}
                {winningArm && (
                  <div className="relative rounded-lg border border-primary/30 bg-gradient-to-b from-primary/[0.04] via-card to-card p-6 shadow-xs space-y-5">
                    {/* Top Bar of Champion Card */}
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs font-semibold border border-emerald-500/20">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            Current Winner · 85% Traffic
                          </span>
                          <span className="text-xs text-muted-foreground">
                            (P(Optimal) = {Math.round((winningArm.win_probability || 0.64) * 100)}%)
                          </span>
                        </div>
                        <h4 className="text-base font-semibold text-foreground tracking-tight pt-1">
                          {winningArm.name}
                        </h4>
                      </div>

                      {/* Conversion Stat Pillar */}
                      <div className="flex items-center gap-3 shrink-0">
                        <div className="flex flex-col items-end px-3.5 py-2 rounded-lg bg-card border border-border shadow-xs">
                          <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                            Reply Rate
                          </span>
                          <div className="flex items-baseline gap-1 mt-0.5">
                            <span className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400 tracking-tight">
                              {Math.round((winningArm.expected_cvr || 0) * 100)}%
                            </span>
                            <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold font-mono">
                              (+17%)
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Live Message Preview Box (Real human text with token badges) */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs text-muted-foreground font-medium px-1">
                        <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                          <Eye className="w-3.5 h-3.5 text-primary" />
                          Live Message Preview
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          {winningArm.template_text?.length || 0} characters
                        </span>
                      </div>

                      <div className="rounded-lg bg-background/80 border border-border/80 p-4 shadow-inner text-sm leading-relaxed text-foreground font-sans">
                        {renderTemplateWithTokens(winningArm.template_text)}
                      </div>
                    </div>

                    {/* Champion Footer & Primary Action */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2 border-t border-border">
                      <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
                        <span>Tested on <strong className="text-foreground">{winningArm.impressions} prospects</strong></span>
                        <span>•</span>
                        <span><strong className="text-emerald-600 dark:text-emerald-400 font-semibold">{winningArm.positive_replies}</strong> positive replies</span>
                        <span>•</span>
                        <span>{winningArm.objections} objections</span>
                        <span>•</span>
                        <span>{winningArm.unsubscribes} unsubscribes</span>
                      </div>

                      <div className="flex items-center gap-2 self-end sm:self-auto">
                        <button
                          type="button"
                          onClick={() => handleCopyText(winningArm.template_text, winningArm.id)}
                          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
                        >
                          {isWinnerCopied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                          <span>{isWinnerCopied ? "Copied" : "Copy Template"}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleApplyToStep(winningArm)}
                          className={`flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                            isWinnerApplied
                              ? 'bg-primary/10 text-primary border border-primary/30'
                              : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm'
                          }`}
                        >
                          {isWinnerApplied ? <CheckCheck className="w-3.5 h-3.5" /> : <ArrowRight className="w-3.5 h-3.5" />}
                          <span>{isWinnerApplied ? "Applied to Sequence" : "Apply to Sequence Step"}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* CHALLENGER TESTING BENCH (2-Column Grid) */}
                {challengerArms.length > 0 && (
                  <div className="space-y-3.5 pt-1">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                          Challenger Testing Bench ({challengerArms.length} Angles)
                        </h4>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          The algorithm routes 15% of outbound volume to these alternatives to test for superior performance.
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {challengerArms.map((arm: any) => {
                        const isDegraded = arm.status === 'degraded';
                        const isApplied = appliedArmId === arm.id;
                        const isCopied = copiedArmId === arm.id;
                        const cvr = Math.round((arm.expected_cvr || 0) * 100);

                        return (
                          <div
                            key={arm.id}
                            className="rounded-lg border border-border bg-card/60 hover:bg-card hover:border-border/80 transition-all p-4 flex flex-col justify-between space-y-3.5"
                          >
                            <div className="space-y-2.5">
                              <div className="flex items-start justify-between gap-3">
                                <div className="space-y-1">
                                  <span className="font-semibold text-xs text-foreground block">
                                    {arm.name}
                                  </span>
                                  {isDegraded ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-muted text-muted-foreground border border-border">
                                      Low Response (0% Traffic)
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-muted text-foreground border border-border">
                                      Testing Challenger (15% Traffic)
                                    </span>
                                  )}
                                </div>

                                <div className="text-right shrink-0">
                                  <span className="text-[10px] text-muted-foreground uppercase font-semibold block">
                                    Reply Rate
                                  </span>
                                  <span className="text-sm font-mono font-bold text-foreground">
                                    {cvr}%
                                  </span>
                                </div>
                              </div>

                              {/* Message Preview with Tokens */}
                              <div className={`rounded-lg bg-background/60 p-3 border border-border text-xs leading-relaxed text-foreground/90 font-sans transition-all ${expandedArmIds[arm.id] ? '' : 'line-clamp-3'}`}>
                                {renderTemplateWithTokens(arm.template_text)}
                              </div>
                              {arm.template_text && arm.template_text.length > 110 && (
                                <button
                                  type="button"
                                  onClick={() => setExpandedArmIds(prev => ({ ...prev, [arm.id]: !prev[arm.id] }))}
                                  className="text-[11px] text-primary hover:underline font-medium self-start cursor-pointer -mt-1 block"
                                >
                                  {expandedArmIds[arm.id] ? "Show less" : "Show full copy"}
                                </button>
                              )}
                            </div>

                            {/* Footer & Actions */}
                            <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/60 text-xs">
                              <span className="text-muted-foreground text-[11px]">
                                {arm.impressions} sent · {arm.positive_replies} replies
                              </span>

                              <div className="flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => handleCopyText(arm.template_text, arm.id)}
                                  className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
                                  title="Copy Template"
                                >
                                  {isCopied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                                </button>

                                <button
                                  type="button"
                                  onClick={() => handleApplyToStep(arm)}
                                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                                    isApplied
                                      ? 'bg-primary/10 text-primary border border-primary/20'
                                      : 'bg-muted text-foreground hover:bg-muted/80 border border-border'
                                  }`}
                                >
                                  {isApplied ? "Applied" : "Apply"}
                                </button>

                                {isDegraded && (
                                  <button
                                    type="button"
                                    onClick={() => handleMutateVariant(arm.id)}
                                    disabled={isMutatingArmId === arm.id}
                                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-primary/10 text-primary border border-primary/20 text-xs font-semibold hover:bg-primary/20 transition-all disabled:opacity-50 cursor-pointer"
                                  >
                                    <RefreshCw className={`w-3 h-3 ${isMutatingArmId === arm.id ? 'animate-spin' : ''}`} />
                                    <span>Rewrite</span>
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

          {/* Tab 2: Lead Trigger Signals */}
          {activeTab === 'triggers' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Real-Time Lead Trigger Radar
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Live detection of executive job changes, funding announcements, and promotions with contextual icebreakers.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={fetchTriggerRadar}
                    disabled={isLoadingTriggers}
                    className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-all cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${isLoadingTriggers ? 'animate-spin' : ''}`} />
                    <span>Scan Now</span>
                  </button>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground pl-2">
                    <span className="flex h-2 w-2 rounded-full bg-primary" />
                    Radar Online
                  </div>
                </div>
              </div>

              {/* Filter Pills */}
              <div className="flex items-center justify-between gap-4 flex-wrap pb-2 border-b border-border">
                <div className="flex items-center gap-1.5 text-xs flex-wrap">
                  <span className="text-muted-foreground font-medium mr-1 flex items-center gap-1">
                    <Filter className="w-3 h-3" /> Signal:
                  </span>
                  {[
                    { id: "ALL", label: "All Signals" },
                    { id: "NEW_ROLE", label: "New Role" },
                    { id: "FUNDING_ROUND", label: "Funding Round" },
                    { id: "PROMOTION", label: "Promotion" },
                    { id: "HIRING_SURGE", label: "SDR Surge" }
                  ].map(tab => (
                    <button
                      type="button"
                      key={tab.id}
                      onClick={() => setTriggerEventTypeFilter(tab.id)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                        triggerEventTypeFilter === tab.id
                          ? 'bg-primary/10 text-primary'
                          : 'bg-muted text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-1.5 text-xs">
                  <span className="text-muted-foreground font-medium mr-1">Status:</span>
                  {[
                    { id: "ALL", label: "All" },
                    { id: "PENDING", label: "Pending" },
                    { id: "ENROLLED", label: "Enrolled" }
                  ].map(s => (
                    <button
                      type="button"
                      key={s.id}
                      onClick={() => setTriggerStatusFilter(s.id)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                        triggerStatusFilter === s.id
                          ? 'bg-primary/10 text-primary'
                          : 'bg-muted text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Triggers Feed */}
              <div className="grid grid-cols-1 gap-4">
                {filteredTriggers.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border p-8 text-center">
                    <Radio className="h-8 w-8 text-muted-foreground mx-auto mb-2 opacity-50" />
                    <p className="text-sm font-medium text-foreground">No trigger events matching active filters</p>
                    <p className="text-xs text-muted-foreground mt-1">Try resetting the filter criteria or click "Scan Now" to refresh.</p>
                  </div>
                ) : (
                  filteredTriggers.map((trigger) => {
                    const isEnrolled = trigger.status === 'ENROLLED';
                    const isBlocked = trigger.status === 'BLOCKED_SUPPRESSED';
                    
                    return (
                      <div
                        key={trigger.id}
                        className={`rounded-lg border p-4 transition-all ${
                          isEnrolled
                            ? 'border-primary/40 bg-primary/5'
                            : isBlocked
                            ? 'border-rose-500/40 bg-rose-500/5'
                            : 'border-border bg-card'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="space-y-2 flex-1">
                            <div className="flex items-center gap-2.5 flex-wrap">
                              {trigger.event_type === 'NEW_ROLE' && (
                                <span className="flex items-center gap-1 rounded-md bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground border border-border">
                                  <Briefcase className="h-3 w-3" />
                                  New Role
                                </span>
                              )}
                              {trigger.event_type === 'FUNDING_ROUND' && (
                                <span className="flex items-center gap-1 rounded-md bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground border border-border">
                                  <DollarSign className="h-3 w-3" />
                                  Funding Round
                                </span>
                              )}
                              {trigger.event_type === 'PROMOTION' && (
                                <span className="flex items-center gap-1 rounded-md bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground border border-border">
                                  <Award className="h-3 w-3" />
                                  Executive Promotion
                                </span>
                              )}
                              {trigger.event_type === 'HIRING_SURGE' && (
                                <span className="flex items-center gap-1 rounded-md bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground border border-border">
                                  <Users className="h-3 w-3" />
                                  SDR Hiring Surge
                                </span>
                              )}

                              <span className="text-xs font-semibold text-foreground">{trigger.prospect_name}</span>
                              <span className="text-xs text-muted-foreground">@ {trigger.company_name}</span>
                              <span className="text-xs text-muted-foreground ml-auto">{trigger.detected_at}</span>
                            </div>

                            {/* Event Details */}
                            <div className="text-xs text-foreground font-medium">
                              {trigger.event_type === 'NEW_ROLE' && `Started as ${trigger.event_data?.new_title || 'VP'} (prev. ${trigger.event_data?.previous_company || 'Peer'})`}
                              {trigger.event_type === 'FUNDING_ROUND' && `Announced ${trigger.event_data?.round_type || 'Round'} (${trigger.event_data?.amount_raised || '$25M'}) led by ${trigger.event_data?.lead_investor || 'Venture Capital'}`}
                              {trigger.event_type === 'PROMOTION' && `Promoted from ${trigger.event_data?.previous_title || 'Director'} to ${trigger.event_data?.new_title || 'Executive'}`}
                              {trigger.event_type === 'HIRING_SURGE' && `Hiring ${trigger.event_data?.open_sales_roles || 'multiple'} SDR roles (${trigger.event_data?.surge_percentage || '+30%'} increase)`}
                            </div>

                            {/* Generated Icebreaker */}
                            <div className="relative rounded-lg bg-background/80 p-3.5 border border-border">
                              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1.5">
                                <Sparkles className="w-3 h-3 text-primary" />
                                Contextual Icebreaker Hook
                              </div>
                              <p className="text-xs text-foreground font-sans leading-relaxed pr-8">
                                {trigger.generated_icebreaker}
                              </p>
                              <button
                                type="button"
                                onClick={() => handleCopyIcebreaker(trigger.generated_icebreaker, trigger.id)}
                                className="absolute top-2.5 right-2.5 text-muted-foreground hover:text-foreground p-1.5 rounded-md hover:bg-muted transition-colors cursor-pointer"
                                title="Copy Icebreaker"
                              >
                                {copiedTriggerId === trigger.id ? (
                                  <Check className="h-4 w-4 text-primary" />
                                ) : (
                                  <Copy className="h-4 w-4" />
                                )}
                              </button>
                            </div>
                          </div>

                          {/* Actions */}
                          <div className="flex flex-col items-end gap-2 shrink-0 pt-1">
                            {isEnrolled ? (
                              <div className="flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary">
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                Enrolled
                              </div>
                            ) : isBlocked ? (
                              <div className="flex items-center gap-1.5 rounded-md bg-rose-500/10 border border-rose-500/20 px-3 py-1.5 text-xs font-medium text-rose-500">
                                <ShieldAlert className="h-3.5 w-3.5" />
                                Suppressed (DNC)
                              </div>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  onClick={() => handleEnrollTrigger(trigger)}
                                  disabled={enrollingTriggerId === trigger.id}
                                  className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer"
                                >
                                  {!isPro ? <Lock className="h-3.5 w-3.5 text-amber-300" /> : <Rocket className="h-3.5 w-3.5" />}
                                  <span>Enroll with Icebreaker</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDismissTrigger(trigger.id)}
                                  className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded-md transition-colors cursor-pointer"
                                >
                                  Dismiss
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* Tab 3: Copy Evolution Studio */}
          {activeTab === 'evolution' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <Brain className="w-4 h-4 text-primary" />
                    Copy Evolution Studio
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Synthesize next-generation challenger angles tailored for {activeTouchpoint.name} with automated token canonicalization & character boundary clamping.
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="rounded-md border border-border bg-card px-2.5 py-1 text-muted-foreground font-mono">
                    Channel: <span className="text-foreground font-semibold uppercase">{activeTouchpoint.channel}</span>
                  </span>
                  {activeTouchpoint.channel === 'linkedin' ? (
                    <span className="rounded-md bg-primary/10 border border-primary/20 px-2.5 py-1 text-primary font-medium">
                      Strict 295 Chars Clamp
                    </span>
                  ) : (
                    <span className="rounded-md bg-primary/10 border border-primary/20 px-2.5 py-1 text-primary font-medium">
                      Subject + Body Architecture
                    </span>
                  )}
                </div>
              </div>

              {/* Section 1: Parent Angle Selector */}
              <div className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <GitBranch className="w-3.5 h-3.5 text-primary" />
                    <span>Select Parent Angle to Mutate From</span>
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    {arms.length} active/tested angles available
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {arms.map((arm) => {
                    const isSelected = selectedParentArmId === arm.id;
                    return (
                      <button
                        key={arm.id}
                        type="button"
                        onClick={() => setSelectedParentArmId(arm.id)}
                        className={`text-left p-3 rounded-lg border transition-all cursor-pointer flex flex-col justify-between ${
                          isSelected
                            ? 'border-primary bg-primary/10 shadow-xs ring-1 ring-primary'
                            : 'border-border bg-background hover:border-primary/40'
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <span className="text-xs font-semibold text-foreground line-clamp-1">{arm.name}</span>
                            {arm.is_winner && (
                              <span className="rounded-md px-1.5 py-0.5 bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20 text-[10px] font-semibold shrink-0">
                                Winner
                              </span>
                            )}
                            {arm.status === 'degraded' && (
                              <span className="rounded-md px-1.5 py-0.5 bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-500/20 text-[10px] font-semibold shrink-0">
                                Degraded
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                            "{arm.template_text}"
                          </p>
                        </div>
                        <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/50 text-[10px] text-muted-foreground font-mono">
                          <span>Traffic: {arm.traffic_allocation || '15%'}</span>
                          <span>CVR: {Math.round((arm.expected_cvr || 0.25) * 100)}%</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Section 2: Framework Selector */}
              <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
                <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-primary" />
                  <span>Select Optimization Framework</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  {[
                    { id: "social_proof_metric", label: "ROI Metric Hook", desc: "Hard data points & case study conversions" },
                    { id: "provocative_question", label: "Provocative Hook", desc: "Challenges status quo & SDR tech debt" },
                    { id: "low_friction_benchmark", label: "Benchmark Teardown", desc: "Free 2-page report or audit offer" },
                    { id: "brevity_direct", label: "Executive Brevity", desc: "Punchy 2-sentence direct ask for VPs" }
                  ].map((theme) => (
                    <button
                      key={theme.id}
                      type="button"
                      onClick={() => setMutationTheme(theme.id)}
                      className={`text-left p-3 rounded-lg border transition-all cursor-pointer ${
                        mutationTheme === theme.id
                          ? 'border-primary bg-primary/10 text-foreground font-semibold shadow-xs ring-1 ring-primary'
                          : 'border-border bg-card text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <div className="text-xs font-semibold text-foreground">{theme.label}</div>
                      <div className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{theme.desc}</div>
                    </button>
                  ))}
                </div>

                <div className="pt-2 flex items-center justify-between flex-wrap gap-3">
                  <div className="text-xs text-muted-foreground">
                    Synthesizes a statistically non-identical copy branch with calibrated exploratory priors (<span className="font-mono text-foreground font-medium">&alpha;=2.0, &beta;=2.0</span>).
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (!isPro) {
                        openPaywall({
                          featureName: "Elesium AI Copy Re-Writer",
                          minTier: "PRO",
                          description: "Synthesize next-generation challenger angles automatically with Elesium AI."
                        });
                        return;
                      }
                      handleSynthesizeChallenger();
                    }}
                    disabled={isSynthesizingCopy}
                    className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer shadow-sm"
                  >
                    {!isPro && <Lock className="h-3.5 w-3.5 text-amber-300" />}
                    {isSynthesizingCopy ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Sparkles className="h-3.5 w-3.5" />
                    )}
                    <span>{isSynthesizingCopy ? "Synthesizing Copy..." : "Synthesize Challenger Angle"}</span>
                  </button>
                </div>
              </div>

              {/* Section 3: Live Synthesized Challenger Preview Card */}
              {synthesizedChallenger && (
                <div className="rounded-lg border border-primary/40 bg-card p-5 space-y-4 shadow-sm animate-in fade-in duration-200">
                  <div className="flex items-center justify-between flex-wrap gap-2 border-b border-border pb-3">
                    <div className="flex items-center gap-2">
                      <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary font-bold text-xs">
                        G{synthesizedChallenger.generation || 2}
                      </span>
                      <div>
                        <div className="text-xs font-semibold text-foreground flex items-center gap-2">
                          <span>{synthesizedChallenger.name}</span>
                          <span className="rounded-md bg-primary/10 text-primary text-[10px] font-semibold px-2 py-0.5 border border-primary/20">
                            Ready for Review
                          </span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Strategy: <span className="font-medium text-foreground">{synthesizedChallenger.theme || mutationTheme}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {activeTouchpoint.channel === 'linkedin' ? (
                        <div className="flex items-center gap-1.5 text-xs">
                          <span className={`px-2.5 py-1 rounded-md text-[11px] font-mono font-medium border ${
                            (synthesizedChallenger.template_text?.length || 0) <= 295
                              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400 font-semibold'
                              : 'bg-rose-500/10 border-rose-500/30 text-rose-700 dark:text-rose-400 font-semibold'
                          }`}>
                            {synthesizedChallenger.template_text?.length || 0} / 295 Chars (LinkedIn Safe)
                          </span>
                        </div>
                      ) : (
                        <span className="px-2.5 py-1 rounded-md bg-blue-500/10 border border-blue-500/30 text-blue-700 dark:text-blue-400 text-[11px] font-semibold">
                          Email Step (Subject + Body)
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Copy Content Preview */}
                  <div className="space-y-3">
                    {activeTouchpoint.channel === 'email' && synthesizedChallenger.subject && (
                      <div className="rounded-lg bg-muted/50 p-3 border border-border">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                          Subject Line
                        </div>
                        <div className="text-xs font-semibold text-foreground font-sans">
                          {renderTemplateWithTokens(synthesizedChallenger.subject)}
                        </div>
                      </div>
                    )}

                    <div className="rounded-lg bg-muted/40 p-3.5 border border-border">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center justify-between">
                        <span>Message Body Preview</span>
                        <span className="text-[10px] lowercase font-mono text-muted-foreground">Tokens highlighted in primary</span>
                      </div>
                      <div className="text-xs text-foreground font-sans leading-relaxed whitespace-pre-wrap">
                        {renderTemplateWithTokens(synthesizedChallenger.template_text)}
                      </div>
                    </div>
                  </div>

                  {/* Decision Actions */}
                  <div className="flex items-center justify-between flex-wrap gap-3 pt-1">
                    <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      <span>Passed merge tag canonicalization and formula injection checks.</span>
                    </p>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setSynthesizedChallenger(null)}
                        className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
                      >
                        Discard / Re-Roll
                      </button>
                      <button
                        type="button"
                        onClick={handleAcceptChallenger}
                        className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all cursor-pointer shadow-xs"
                      >
                        <Rocket className="w-3.5 h-3.5" />
                        <span>Accept & Add to Challenger Bench</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Section 4: Dynamic Generation Lineage Timeline */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-primary" />
                    <span>Generation Lineage Timeline</span>
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    {generationHistory.length} total generations tracked
                  </span>
                </div>

                <div className="space-y-2">
                  {generationHistory.map((item, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-lg border border-border bg-card p-3.5 text-xs hover:border-primary/30 transition-all"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary font-semibold text-xs shrink-0">
                          G{item.generation}
                        </div>
                        <div>
                          <div className="font-semibold text-foreground">{item.name}</div>
                          <div className="text-xs text-muted-foreground font-mono">"{item.snippet}"</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-right shrink-0">
                        <div>
                          <div className="text-[10px] text-muted-foreground font-medium">Status / Allocation</div>
                          <div className="font-semibold text-foreground font-mono">{item.cvr}</div>
                        </div>
                        <span className={`rounded-md px-2.5 py-0.5 text-xs font-medium capitalize ${
                          item.status === 'active' || item.status === 'challenger'
                            ? 'bg-primary/10 text-primary border border-primary/20'
                            : 'bg-muted text-muted-foreground border border-border'
                        }`}>
                          {item.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-6 py-4 bg-background">
          <span className="text-xs text-muted-foreground">
            Multi-Armed Bandit Copy Optimization
          </span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border bg-card px-4 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              Close Studio
            </button>
          )}
        </div>

        {/* Add Custom Variation Modal */}
        {showAddArmModal && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto">
            <div className="relative w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <Plus className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-semibold text-foreground">
                    Add Variation for {activeTouchpoint.name}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddArmModal(false)}
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleAddCustomArm} className="space-y-4 text-xs">
                <div>
                  <label className="block font-semibold text-foreground mb-1">Variation Name / Angle</label>
                  <input
                    type="text"
                    value={newArmName}
                    onChange={(e) => setNewArmName(e.target.value)}
                    placeholder="e.g. Founder-to-Founder Low Friction"
                    maxLength={120}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary transition-colors"
                    required
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block font-semibold text-foreground">
                      Message Copy
                    </label>
                    <span className="text-xs text-muted-foreground">
                      Click tags to insert at cursor:
                    </span>
                  </div>

                  {/* Variable insertion pills */}
                  <div className="flex items-center gap-1.5 mb-2 flex-wrap">
                    {['{{first_name}}', '{{company}}', '{{job_title}}', '{{location}}'].map((tag) => (
                      <button
                        type="button"
                        key={tag}
                        onClick={() => handleInsertTag(tag)}
                        className="px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-mono hover:bg-primary/20 transition-colors cursor-pointer"
                      >
                        + {tag}
                      </button>
                    ))}
                  </div>

                  <textarea
                    ref={textareaRef}
                    rows={4}
                    value={newArmTemplate}
                    onChange={(e) => setNewArmTemplate(e.target.value)}
                    placeholder="Hey {{first_name}}, saw your team's expansion at {{company}}..."
                    maxLength={2000}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono text-xs leading-relaxed"
                    required
                  />
                  <div className="flex items-center justify-between mt-1 text-[11px]">
                    <span className="text-muted-foreground">
                      {activeTouchpoint.contextHint}
                    </span>
                    <span
                      className={`font-mono font-medium shrink-0 ml-2 ${
                        activeTouchpoint.charLimit && newArmTemplate.length > activeTouchpoint.charLimit
                          ? "text-destructive font-bold"
                          : activeTouchpoint.charLimit && newArmTemplate.length >= activeTouchpoint.charLimit * 0.9
                          ? "text-amber-600 dark:text-amber-400"
                          : "text-muted-foreground"
                      }`}
                    >
                      {newArmTemplate.length}
                      {activeTouchpoint.charLimit ? ` / ${activeTouchpoint.charLimit}` : ""} chars
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setShowAddArmModal(false)}
                    className="rounded-lg border border-border bg-background px-3 py-1.5 font-medium text-foreground hover:bg-muted cursor-pointer transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={
                      isSubmittingNewArm ||
                      !newArmName.trim() ||
                      !newArmTemplate.trim() ||
                      Boolean(activeTouchpoint.charLimit && newArmTemplate.length > activeTouchpoint.charLimit)
                    }
                    className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-1.5 font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 cursor-pointer transition-all"
                  >
                    {isSubmittingNewArm && <RefreshCw className="h-3 w-3 animate-spin" />}
                    <span>Deploy Variation</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
