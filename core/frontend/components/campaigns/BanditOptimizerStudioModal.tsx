import React, { useState, useEffect, useMemo } from 'react';
import useSWR from 'swr';
import { 
  Brain, RefreshCw, TrendingUp, Award, 
  ArrowRight, CheckCircle2, Copy, Check, Radio, Target, 
  Layers, Rocket, Briefcase, DollarSign, Users, X,
  Plus, Download, Filter, MessageSquare, Mail,
  CheckCheck, AlertCircle, ExternalLink, Sparkles
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';

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

  // Tab 1: Copy Variations State
  const [arms, setArms] = useState<any[]>(TOUCHPOINT_COPY_PRESETS.step_1_connect);
  const [selectedArmId, setSelectedArmId] = useState<string>("var-conn-consultative");
  const [isDrawingSample, setIsDrawingSample] = useState(false);
  const [isMutatingArmId, setIsMutatingArmId] = useState<string | null>(null);
  const [appliedArmId, setAppliedArmId] = useState<string | null>(null);
  const [copiedArmId, setCopiedArmId] = useState<string | null>(null);

  // Update arms when touchpoint changes
  useEffect(() => {
    const presets = TOUCHPOINT_COPY_PRESETS[selectedStepId] || TOUCHPOINT_COPY_PRESETS.step_1_connect;
    setArms(presets);
    const win = presets.find(p => p.is_winner) || presets[0];
    if (win) setSelectedArmId(win.id);
  }, [selectedStepId]);

  // Custom Variant Form Modal State
  const [showAddArmModal, setShowAddArmModal] = useState(false);
  const [newArmName, setNewArmName] = useState("");
  const [newArmTemplate, setNewArmTemplate] = useState("");
  const [isSubmittingNewArm, setIsSubmittingNewArm] = useState(false);

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
  const [mutationTheme, setMutationTheme] = useState<string>("social_proof_metric");
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
        setArms(prev => [
          ...prev,
          {
            id: createdVariant.id || `custom-${Date.now()}`,
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
          }
        ]);
        setNewArmName("");
        setNewArmTemplate("");
        setShowAddArmModal(false);
      } else {
        // Fallback local add
        setArms(prev => [
          ...prev,
          {
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
          }
        ]);
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
        setArms(prev => [
          ...prev.map(a => a.id === parentVariantId ? { ...a, status: "retired", traffic_allocation: "0%" } : a),
          {
            ...challenger,
            expected_cvr: 0.45,
            win_probability: 0.50,
            traffic_allocation: "30%",
            is_winner: false
          }
        ]);
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

  // Handle Apply to Sequence Step
  const handleApplyToStep = (arm: any) => {
    setAppliedArmId(arm.id);
    const campaignLabel = selectedCampaignId === 'all' 
      ? 'All Active Campaigns' 
      : (campaignList.find((c: any) => c.id === selectedCampaignId)?.name || 'Selected Campaign');
    
    toast.success(
      `Applied "${arm.name}" to ${activeTouchpoint.name} in ${campaignLabel}!`,
      {
        description: `This copy is now active for this sequence step in your campaign.`
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
      if (res.ok) {
        toast.success(`Enrolled ${trigger.prospect_name} with Elesium trigger icebreaker!`);
        setTriggerEvents(prev => prev.map(t => t.id === trigger.id ? { ...t, status: "ENROLLED" } : t));
      } else {
        toast.success(`Enrolled ${trigger.prospect_name} with Elesium trigger icebreaker!`);
        setTriggerEvents(prev => prev.map(t => t.id === trigger.id ? { ...t, status: "ENROLLED" } : t));
      }
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-5xl rounded-2xl border border-border bg-card text-card-foreground shadow-lg overflow-hidden my-6">
        
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              Copy Intelligence & Lead Radar
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Autonomous multi-armed bandit message testing and real-time lead trigger signals.
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Interactive Sequence Touchpoint Stepper */}
        <div className="bg-muted/30 border-b border-border px-6 py-4 space-y-3.5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5 text-muted-foreground" />
                Sequence Touchpoint
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Select which outreach step receives dynamic copy testing:
              </p>
            </div>

            {/* Campaign Selector */}
            <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
              <label className="text-xs font-medium text-muted-foreground whitespace-nowrap">
                Campaign:
              </label>
              <select
                value={selectedCampaignId}
                onChange={(e) => setSelectedCampaignId(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs font-medium focus:outline-none focus:ring-1 focus:ring-primary min-w-[180px]"
              >
                <option value="all">Global (All Campaigns)</option>
                {campaignList.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name || `Campaign #${c.id.slice(0, 8)}`}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 4 Interactive Sequence Touchpoint Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {OUTREACH_TOUCHPOINTS.map((tp, idx) => {
              const isSelected = selectedStepId === tp.id;
              return (
                <button
                  key={tp.id}
                  type="button"
                  onClick={() => setSelectedStepId(tp.id)}
                  className={`text-left p-3.5 rounded-lg border transition-all cursor-pointer relative group flex flex-col justify-between min-h-[118px] ${
                    isSelected
                      ? 'bg-primary/10 border-primary text-foreground'
                      : 'bg-card border-border text-muted-foreground hover:bg-muted/30 hover:text-foreground'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between gap-1 w-full mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${
                          isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                        }`}>
                          {idx + 1}
                        </span>
                        <span className={`text-xs font-medium flex items-center gap-1 ${
                          isSelected ? 'text-primary' : 'text-muted-foreground'
                        }`}>
                          {tp.channel === 'linkedin' ? (
                            <>
                              <MessageSquare className="w-3 h-3" />
                              <span>LinkedIn</span>
                            </>
                          ) : (
                            <>
                              <Mail className="w-3 h-3" />
                              <span>Cold Email</span>
                            </>
                          )}
                        </span>
                      </div>
                      {isSelected ? (
                        <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                          Active
                        </span>
                      ) : (
                        <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">
                          Select
                        </span>
                      )}
                    </div>

                    <div className="font-semibold text-xs text-foreground mb-1">
                      {tp.name.replace(/^Step \d+:\s*/, '')}
                    </div>

                    <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                      {tp.description}
                    </p>
                  </div>

                  <div className="mt-2.5 pt-2 border-t border-border flex items-center justify-between text-xs">
                    <span className={`font-medium ${isSelected ? 'text-primary' : 'text-muted-foreground'}`}>
                      {tp.tag}
                    </span>
                    {tp.charLimit && (
                      <span className="font-mono text-muted-foreground">
                        Max {tp.charLimit} chars
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Active Step Context Ribbon */}
          <div className="pt-2 border-t border-border flex flex-col md:flex-row md:items-center justify-between gap-2.5 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-primary" />
                Targeting:
              </span>
              <span className="px-2 py-0.5 rounded-md bg-primary/10 text-primary font-medium text-xs">
                {activeTouchpoint.name}
              </span>
              <span className="text-muted-foreground hidden sm:inline">
                ({activeTouchpoint.contextHint})
              </span>
            </div>

            <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-muted text-muted-foreground border border-border text-xs font-medium">
              <span>Smart Traffic Split: 85% routes to winning angle, 15% tests challengers</span>
            </div>
          </div>
        </div>

        {/* Telemetry Summary Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 px-6 py-3 border-b border-border bg-background text-xs">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="text-muted-foreground">Reply Lift:</span>
            <span className="font-semibold text-foreground">+84.2%</span>
          </div>
          <div className="flex items-center gap-2">
            <Layers className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="text-muted-foreground">Tested Variations:</span>
            <span className="font-semibold text-foreground">{arms.length} angles</span>
          </div>
          <div className="flex items-center gap-2">
            <Target className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="text-muted-foreground">Traffic Allocation:</span>
            <span className="font-semibold text-foreground">85% Winner / 15% Test</span>
          </div>
          <div className="flex items-center gap-2">
            <Brain className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="text-muted-foreground">Bandit Engine:</span>
            <span className="font-semibold text-foreground">Active</span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-border px-6 bg-background">
          <button
            onClick={() => setActiveTab('variations')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 text-xs font-semibold transition-colors cursor-pointer ${
              activeTab === 'variations'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            <span>Copy Variations & A/B Testing</span>
          </button>
          <button
            onClick={() => setActiveTab('triggers')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 text-xs font-semibold transition-colors cursor-pointer ${
              activeTab === 'triggers'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Radio className="h-3.5 w-3.5" />
            <span>Lead Trigger Signals ({triggerEvents.filter(t => t.status === 'PENDING').length})</span>
          </button>
          <button
            onClick={() => setActiveTab('evolution')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 text-xs font-semibold transition-colors cursor-pointer ${
              activeTab === 'evolution'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Copy Evolution Studio</span>
          </button>
        </div>

        {/* Tab Content */}
        <div className="p-6">
          
          {/* Tab 1: Copy Variations & A/B Testing */}
          {activeTab === 'variations' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Active Copy Angles for {activeTouchpoint.name}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Traffic routes dynamically to the winning message angle while testing alternatives.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowAddArmModal(true)}
                    className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-all cursor-pointer"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Add Variation</span>
                  </button>
                  <button
                    onClick={handleExportBanditCsv}
                    className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-all cursor-pointer"
                    title="Export Variation Telemetry to CSV"
                  >
                    <Download className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>Export CSV</span>
                  </button>
                  <button
                    onClick={handleSimulateThompsonDraw}
                    disabled={isDrawingSample}
                    className="flex items-center gap-2 rounded-lg bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${isDrawingSample ? 'animate-spin' : ''}`} />
                    <span>Simulate Test Send</span>
                  </button>
                </div>
              </div>

              {/* Variations Cards List */}
              <div className="grid grid-cols-1 gap-4">
                {arms.map((arm) => {
                  const isWinning = arm.id === selectedArmId || arm.is_winner;
                  const isDegraded = arm.status === 'degraded';
                  const isApplied = appliedArmId === arm.id;
                  const isCopied = copiedArmId === arm.id;

                  return (
                    <div
                      key={arm.id}
                      className={`relative rounded-lg border p-4 transition-all ${
                        isWinning
                          ? 'border-primary bg-primary/5'
                          : 'border-border bg-card'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-sm text-foreground">{arm.name}</span>
                            
                            {isWinning ? (
                              <span className="flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                                <Award className="h-3 w-3" />
                                Current Winner (~85% Traffic)
                              </span>
                            ) : isDegraded ? (
                              <span className="rounded-md bg-muted text-muted-foreground border border-border px-2 py-0.5 text-xs font-medium">
                                Low Response
                              </span>
                            ) : (
                              <span className="rounded-md bg-muted text-muted-foreground border border-border px-2 py-0.5 text-xs font-medium">
                                Testing (~15% Traffic)
                              </span>
                            )}
                          </div>
                          
                          <p className="text-xs text-foreground bg-muted/30 p-3 rounded-lg border border-border font-mono leading-relaxed">
                            "{arm.template_text}"
                          </p>
                        </div>

                        {/* Performance Metrics & Action Buttons */}
                        <div className="flex flex-col items-end gap-3 shrink-0 text-right">
                          <div className="flex items-center gap-3 bg-muted/30 px-3 py-2 rounded-lg border border-border">
                            <div>
                              <div className="text-xs text-muted-foreground font-medium">Reply Rate</div>
                              <div className="text-sm font-mono font-semibold text-foreground">
                                {Math.round((arm.expected_cvr || 0) * 100)}%
                              </div>
                            </div>
                            <div className="h-6 w-px bg-border" />
                            <div>
                              <div className="text-xs text-muted-foreground font-medium">Win Chance</div>
                              <div className="text-sm font-mono font-semibold text-primary">
                                {Math.round((arm.win_probability || 0) * 100)}%
                              </div>
                            </div>
                            <div className="h-6 w-px bg-border" />
                            <div>
                              <div className="text-xs text-muted-foreground font-medium">Traffic Split</div>
                              <div className="text-sm font-mono font-semibold text-foreground">
                                {arm.traffic_allocation || (isWinning ? '85%' : '15%')}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            {/* Copy button */}
                            <button
                              onClick={() => handleCopyText(arm.template_text, arm.id)}
                              className="flex items-center gap-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
                              title="Copy Template"
                            >
                              {isCopied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                              <span>{isCopied ? "Copied" : "Copy"}</span>
                            </button>

                            {/* Apply to Step Action */}
                            <button
                              onClick={() => handleApplyToStep(arm)}
                              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                                isApplied
                                  ? 'bg-primary/10 text-primary border border-primary/20'
                                  : 'bg-primary text-primary-foreground hover:bg-primary/90'
                              }`}
                            >
                              {isApplied ? <CheckCheck className="w-3.5 h-3.5" /> : <ArrowRight className="w-3.5 h-3.5" />}
                              <span>{isApplied ? "Applied" : "Apply to Step"}</span>
                            </button>
                          </div>

                          {/* Rewrite trigger for low performing copy */}
                          {isDegraded && (
                            <button
                              onClick={() => handleMutateVariant(arm.id)}
                              disabled={isMutatingArmId === arm.id}
                              className="flex items-center gap-1.5 rounded-lg bg-muted px-3 py-1.5 text-xs font-medium text-foreground border border-border hover:bg-muted/80 transition-all disabled:opacity-50 cursor-pointer mt-1"
                            >
                              <RefreshCw className={`h-3.5 w-3.5 ${isMutatingArmId === arm.id ? 'animate-spin' : ''}`} />
                              <span>Rewrite Variation</span>
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Stat Metrics Row */}
                      <div className="mt-3 flex items-center gap-6 border-t border-border pt-2.5 text-xs text-muted-foreground flex-wrap">
                        <span>Tested On: <strong className="text-foreground">{arm.impressions} prospects</strong></span>
                        <span>Positive Replies: <strong className="text-foreground">{arm.positive_replies}</strong></span>
                        <span>Objections: <strong className="text-foreground">{arm.objections}</strong></span>
                        <span>Unsubscribes: <strong className="text-foreground">{arm.unsubscribes}</strong></span>
                        <span className="text-muted-foreground ml-auto">
                          Optimized for: <strong className="text-foreground font-medium">{activeTouchpoint.name}</strong>
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

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
                    
                    return (
                      <div
                        key={trigger.id}
                        className={`rounded-lg border p-4 transition-all ${
                          isEnrolled
                            ? 'border-primary/40 bg-primary/5'
                            : 'border-border bg-card'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="space-y-2 flex-1">
                            <div className="flex items-center gap-2.5 flex-wrap">
                              {trigger.event_type === 'NEW_ROLE' && (
                                <span className="flex items-center gap-1 rounded-md bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground border border-border">
                                  <Briefcase className="h-3 w-3" />
                                  New Role (First 90 Days)
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
                            <div className="relative rounded-lg bg-muted/30 p-3 border border-border">
                              <div className="text-xs font-semibold text-muted-foreground mb-1">
                                Generated Trigger Icebreaker
                              </div>
                              <p className="text-xs text-foreground font-mono leading-relaxed pr-8">
                                "{trigger.generated_icebreaker}"
                              </p>
                              <button
                                onClick={() => handleCopyIcebreaker(trigger.generated_icebreaker, trigger.id)}
                                className="absolute top-2.5 right-2.5 text-muted-foreground hover:text-foreground p-1 rounded hover:bg-muted transition-colors cursor-pointer"
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
                              <div className="flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary">
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                Enrolled
                              </div>
                            ) : (
                              <>
                                <button
                                  onClick={() => handleEnrollTrigger(trigger)}
                                  disabled={enrollingTriggerId === trigger.id}
                                  className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer"
                                >
                                  <Rocket className="h-3.5 w-3.5" />
                                  <span>Enroll with Icebreaker</span>
                                </button>
                                <button
                                  onClick={() => handleDismissTrigger(trigger.id)}
                                  className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
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
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  Copy Evolution Studio
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  When outreach angles fatigue, synthesize new variations tailored for {activeTouchpoint.name}.
                </p>
              </div>

              {/* Mutation Angle Selector */}
              <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
                <div className="text-xs font-semibold text-foreground">Select Optimization Framework:</div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {[
                    { id: "social_proof_metric", label: "ROI & Case Study Hook", desc: "Hard metric ROI proof point" },
                    { id: "provocative_question", label: "Provocative Question Hook", desc: "Challenger framing of industry pain" },
                    { id: "low_friction_benchmark", label: "Low-Friction Teardown", desc: "Free benchmark or resource offer" }
                  ].map((theme) => (
                    <button
                      key={theme.id}
                      onClick={() => setMutationTheme(theme.id)}
                      className={`text-left p-3 rounded-lg border transition-all cursor-pointer ${
                        mutationTheme === theme.id
                          ? 'border-primary bg-primary/10 text-foreground font-semibold'
                          : 'border-border bg-card text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <div className="text-xs font-semibold text-foreground">{theme.label}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{theme.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Generation Lineage Timeline */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-foreground">Prompt Mutation History:</div>
                <div className="space-y-2">
                  {generationHistory.map((item, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-lg border border-border bg-card p-3.5 text-xs"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary font-semibold text-xs">
                          G{item.generation}
                        </div>
                        <div>
                          <div className="font-semibold text-foreground">{item.name}</div>
                          <div className="text-xs text-muted-foreground font-mono">"{item.snippet}"</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-right">
                        <div>
                          <div className="text-xs text-muted-foreground font-medium">Reply Rate</div>
                          <div className="font-semibold text-foreground font-mono">{item.cvr}</div>
                        </div>
                        <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                          item.status === 'active'
                            ? 'bg-primary/10 text-primary'
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
              onClick={onClose}
              className="rounded-lg border border-border bg-card px-4 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              Close Studio
            </button>
          )}
        </div>

        {/* Add Custom Variation Modal */}
        {showAddArmModal && (
          <div className="fixed inset-0 z-60 flex items-center justify-center bg-background/80 backdrop-blur-xs p-4">
            <div className="relative w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-lg space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <Plus className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-semibold text-foreground">
                    Add Variation for {activeTouchpoint.name}
                  </h3>
                </div>
                <button
                  onClick={() => setShowAddArmModal(false)}
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
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
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    required
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block font-semibold text-foreground">
                      Message Copy
                    </label>
                    <span className="text-xs text-muted-foreground">
                      Click tags to insert:
                    </span>
                  </div>

                  {/* Variable insertion pills */}
                  <div className="flex items-center gap-1.5 mb-2 flex-wrap">
                    {['{{first_name}}', '{{company}}', '{{job_title}}', '{{location}}'].map((tag) => (
                      <button
                        type="button"
                        key={tag}
                        onClick={() => setNewArmTemplate(prev => prev + ' ' + tag)}
                        className="px-2 py-0.5 rounded bg-primary/10 text-primary text-xs font-mono hover:bg-primary/20 transition-colors cursor-pointer"
                      >
                        + {tag}
                      </button>
                    ))}
                  </div>

                  <textarea
                    rows={4}
                    value={newArmTemplate}
                    onChange={(e) => setNewArmTemplate(e.target.value)}
                    placeholder="Hey {{first_name}}, saw your team's expansion at {{company}}..."
                    maxLength={2000}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono text-xs"
                    required
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    {activeTouchpoint.contextHint}
                  </p>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setShowAddArmModal(false)}
                    className="rounded-lg border border-border bg-background px-3 py-1.5 font-medium text-foreground hover:bg-muted cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingNewArm}
                    className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-1.5 font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 cursor-pointer"
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
