import React, { useState, useEffect, useRef } from 'react';
import useSWR from 'swr';
import { 
  Users, Mic, Video, RefreshCw, CheckCircle2, Copy, Check, 
  ExternalLink, Play, Pause, Layers, Radio, ShieldAlert, Rocket, X, 
  ChevronRight, Volume2, Film, Filter, Download, Trash2, CheckSquare, Square
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface EventMultimodalStudioProps {
  onClose?: () => void;
  campaignId?: string;
}

interface Attendee {
  id: string;
  prospect_name: string;
  company_name: string;
  title: string;
  linkedin_url: string;
  seniority: string;
  status: string;
  generated_icebreaker: string;
  enrolled_campaign_id?: string;
}

interface MultimodalAsset {
  id: string;
  workspace_id?: string;
  asset_type: 'voice_script' | 'video_card';
  script_text: string;
  estimated_duration_sec: number;
  media_url?: string | null;
  thumbnail_text?: string | null;
  status: string;
  created_at?: string;
}

export function EventMultimodalStudioModal({ onClose, campaignId }: EventMultimodalStudioProps) {
  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  const [activeTab, setActiveTab] = useState<'events' | 'voice' | 'video' | 'library'>('events');

  // Keyboard navigation & Escape dismiss
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onClose) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Tab 1: Event & Group Harvester State
  const [eventUrl, setEventUrl] = useState("https://www.linkedin.com/events/b2b-ai-outbound-summit-2026-7248921/");
  const [eventName, setEventName] = useState("B2B AI Outbound Summit 2026");
  const [isHarvesting, setIsHarvesting] = useState(false);
  const [seniorityFilter, setSeniorityFilter] = useState<string>("all");
  const [selectedAttendeeIds, setSelectedAttendeeIds] = useState<Set<string>>(new Set(["att-1", "att-2"]));
  const [expandedIcebreakerIds, setExpandedIcebreakerIds] = useState<Set<string>>(new Set());
  const [isEnrollingBatch, setIsEnrollingBatch] = useState(false);
  const [copiedIcebreakerId, setCopiedIcebreakerId] = useState<string | null>(null);
  const [isExportingAttendees, setIsExportingAttendees] = useState(false);

  const toggleExpandIcebreaker = (id: string) => {
    setExpandedIcebreakerIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const [attendees, setAttendees] = useState<Attendee[]>([
    {
      id: "att-1",
      prospect_name: "Alexander Hayes",
      company_name: "NorthStar Data",
      title: "VP of Global Sales",
      linkedin_url: "https://linkedin.com/in/alex-hayes-sales",
      seniority: "vp",
      status: "pending",
      generated_icebreaker: "Alexander, noticed you were also registered for the B2B AI Outbound Summit! Curious how NorthStar Data is rethinking SDR message deliverability this year?"
    },
    {
      id: "att-2",
      prospect_name: "Claire Dupont",
      company_name: "SaaSMetric Labs",
      title: "Chief Revenue Officer",
      linkedin_url: "https://linkedin.com/in/claire-dupont-cro",
      seniority: "c_level",
      status: "pending",
      generated_icebreaker: "Claire, saw you attending the B2B AI Outbound Summit. Given your focus at SaaSMetric Labs, would love to compare notes on pipeline conversion benchmarks."
    },
    {
      id: "att-3",
      prospect_name: "David Ramirez",
      company_name: "CloudFleet Solutions",
      title: "Director of Business Development",
      linkedin_url: "https://linkedin.com/in/david-ramirez-bdr",
      seniority: "director",
      status: "pending",
      generated_icebreaker: "David - saw you on the attendee list for the Outbound Summit! Are your BDRs at CloudFleet testing multi-channel LinkedIn pre-warming yet?"
    },
    {
      id: "att-4",
      prospect_name: "Megan Thorne",
      company_name: "Zeta Scale AI",
      title: "Head of Enterprise Growth",
      linkedin_url: "https://linkedin.com/in/megan-thorne-growth",
      seniority: "director",
      status: "pending",
      generated_icebreaker: "Megan, saw your profile in the Outbound Summit attendee directory! Really resonated with discussions on SDR ramp time."
    }
  ]);

  // Tab 2: Voice Note Studio State
  const [voiceLeadName, setVoiceLeadName] = useState("Jessica Vance");
  const [voiceCompany, setVoiceCompany] = useState("Nexis Corp");
  const [voiceTitle, setVoiceTitle] = useState("VP Revenue Operations");
  const [voiceTone, setVoiceTone] = useState<"casual_peer" | "executive_brief" | "provocative_observation">("casual_peer");
  const [customPainPoint, setCustomPainPoint] = useState("SDR email deliverability drop-off");
  const [isGeneratingVoice, setIsGeneratingVoice] = useState(false);
  const [generatedScript, setGeneratedScript] = useState<string>(
    "Hey Jessica! [pause] Thought I'd send a quick voice note instead of crowding your inbox with another pitch. " +
    "Saw what you're building at Nexis Corp - really impressive trajectory. " +
    "We put together a short teardown on how B2B teams are doubling meeting conversions without burning their domain reputation. " +
    "[pause] Would you be opposed if I sent it over to glance at?"
  );
  const [estimatedDuration, setEstimatedDuration] = useState<number>(24);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [copiedVoiceScript, setCopiedVoiceScript] = useState(false);
  const speechUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  // Tab 3: Video Prospecting Card State
  const [videoLeadName, setVideoLeadName] = useState("Marcus Vance");
  const [videoCompany, setVideoCompany] = useState("Apex Cloud");
  const [videoTopic, setVideoTopic] = useState("60s Outbound Pipeline Audit");
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [generatedVideoCard, setGeneratedVideoCard] = useState<any>({
    thumbnail_title: "Custom 60s Outbound Pipeline Audit for Marcus @ Apex Cloud",
    video_url: "https://elein.app/v/apex-cloud-60s-teardown",
    dm_copy: "Hey Marcus - put together a personalized 60-second video walkthrough showing how Apex Cloud can unlock 2x more meetings from target accounts: https://elein.app/v/apex-cloud-60s-teardown",
    estimated_duration_sec: 58
  });
  const [copiedVideoDm, setCopiedVideoDm] = useState(false);

  // Tab 4: Multimodal Assets Library State
  const [savedAssets, setSavedAssets] = useState<MultimodalAsset[]>([]);
  const [isLoadingAssets, setIsLoadingAssets] = useState(false);
  const [libraryFilter, setLibraryFilter] = useState<'all' | 'voice_script' | 'video_card'>('all');
  const [isExportingAssets, setIsExportingAssets] = useState(false);

  // Initial load for attendees
  useEffect(() => {
    async function loadEvents() {
      try {
        const res = await fetchWithAuth("/api/elein/events-multimodal/events/list");
        if (res.ok) {
          const data = await res.json();
          if (data.attendees && data.attendees.length > 0) {
            setAttendees(data.attendees);
          }
        }
      } catch (e) {
        // Retain initial resilient seeds
      }
    }
    loadEvents();
  }, []);

  // Load multimodal assets library when library tab is accessed
  const loadMultimodalAssets = async () => {
    setIsLoadingAssets(true);
    try {
      const url = libraryFilter === 'all' 
        ? '/api/elein/events-multimodal/multimodal/assets'
        : `/api/elein/events-multimodal/multimodal/assets?asset_type=${libraryFilter}`;
      const res = await fetchWithAuth(url);
      if (res.ok) {
        const data = await res.json();
        setSavedAssets(data.assets || []);
      }
    } catch (e) {
      console.error("Failed to load multimodal assets", e);
    } finally {
      setIsLoadingAssets(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'library') {
      loadMultimodalAssets();
    }
  }, [activeTab, libraryFilter]);

  // Cleanup speech synthesis on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Audio Playback Simulation via Web Speech API
  const handleToggleAudio = () => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      setIsPlayingAudio(!isPlayingAudio);
      return;
    }

    if (isPlayingAudio) {
      window.speechSynthesis.cancel();
      setIsPlayingAudio(false);
    } else {
      window.speechSynthesis.cancel();
      const cleanSpokenText = generatedScript.replace(/\[pause\]/gi, " ... ");
      const utterance = new SpeechSynthesisUtterance(cleanSpokenText);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.onend = () => setIsPlayingAudio(false);
      utterance.onerror = () => setIsPlayingAudio(false);
      speechUtteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
      setIsPlayingAudio(true);
    }
  };

  // Handle Event Harvest
  const handleHarvestEvent = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "LinkedIn Event & Group Harvester",
        minTier: "PRO",
        description: "Harvest verified attendees from LinkedIn events, webinars, and specialized groups."
      });
      return;
    }
    setIsHarvesting(true);
    try {
      const res = await fetchWithAuth("/api/elein/events-multimodal/events/harvest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_url: eventUrl,
          event_name: eventName
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "LinkedIn Event & Group Harvester",
          minTier: "PRO",
          description: "Harvest verified attendees from LinkedIn events, webinars, and specialized groups."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || "Harvested attendees successfully!");
        if (data.attendees) {
          setAttendees(prev => [...data.attendees, ...prev]);
        }
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to harvest event attendees." }));
        toast.error(err.detail || "Failed to harvest event attendees.");
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error while harvesting event attendees.");
    } finally {
      setIsHarvesting(false);
    }
  };

  // Toggle Attendee Selection
  const toggleAttendeeSelection = (id: string) => {
    setSelectedAttendeeIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Select / Deselect All (Filter-aware)
  const handleToggleSelectAll = () => {
    const enrollable = filteredAttendees.filter(a => a.status !== 'enrolled');
    if (enrollable.length === 0) return;
    const allFilteredSelected = enrollable.every(a => selectedAttendeeIds.has(a.id));
    setSelectedAttendeeIds(prev => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        enrollable.forEach(a => next.delete(a.id));
      } else {
        enrollable.forEach(a => next.add(a.id));
      }
      return next;
    });
  };

  // Batch Enroll Attendees
  const handleBatchEnroll = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Batch Event Attendee Enrollment",
        minTier: "PRO",
        description: "Enroll event attendees directly into automated outreach sequences."
      });
      return;
    }
    if (selectedAttendeeIds.size === 0) {
      toast.error("Please select at least one attendee to enroll.");
      return;
    }
    setIsEnrollingBatch(true);
    try {
      const res = await fetchWithAuth("/api/elein/events-multimodal/events/enroll-attendees", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          attendee_ids: Array.from(selectedAttendeeIds),
          campaign_id: campaignId || "camp-event-sequence"
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "Batch Event Attendee Enrollment",
          minTier: "PRO",
          description: "Enroll event attendees directly into automated outreach sequences."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || "Successfully enrolled selected attendees!");
        setAttendees(prev => prev.map(a => selectedAttendeeIds.has(a.id) ? { ...a, status: "enrolled" } : a));
        setSelectedAttendeeIds(new Set());
      } else {
        const err = await res.json().catch(() => ({ detail: "Enrollment failed" }));
        toast.error(err.detail || "Failed to batch enroll attendees.");
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error enrolling attendees.");
    } finally {
      setIsEnrollingBatch(false);
    }
  };

  // Export Attendees CSV
  const handleExportAttendeesCsv = async () => {
    setIsExportingAttendees(true);
    try {
      const res = await fetchWithAuth(`/api/elein/events-multimodal/events/export-attendees-csv?seniority=${seniorityFilter}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `event_attendees_${seniorityFilter}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        toast.success("Downloaded attendees CSV with formula sanitization.");
      } else {
        toast.error("Failed to export attendees CSV.");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error exporting attendees CSV.");
    } finally {
      setIsExportingAttendees(false);
    }
  };

  // Export Multimodal Assets CSV
  const handleExportAssetsCsv = async (assetType?: string) => {
    setIsExportingAssets(true);
    try {
      const param = assetType ? `?asset_type=${assetType}` : '';
      const res = await fetchWithAuth(`/api/elein/events-multimodal/multimodal/export-assets-csv${param}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `multimodal_assets_${assetType || 'all'}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        toast.success("Downloaded multimodal assets CSV with formula defense.");
      } else {
        toast.error("Failed to export assets CSV.");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error exporting assets CSV.");
    } finally {
      setIsExportingAssets(false);
    }
  };

  // Delete Multimodal Asset
  const handleDeleteAsset = async (assetId: string) => {
    try {
      const res = await fetchWithAuth(`/api/elein/events-multimodal/multimodal/assets/${assetId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        setSavedAssets(prev => prev.filter(a => a.id !== assetId));
        toast.success("Deleted asset successfully.");
      } else {
        toast.error("Failed to delete asset.");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error deleting asset.");
    }
  };

  // Synthesize Voice Note Script
  const handleGenerateVoiceScript = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "AI Voice Note Script Generator",
        minTier: "PRO",
        description: "Synthesize high-converting conversational audio drops and voice scripts."
      });
      return;
    }
    setIsGeneratingVoice(true);
    try {
      const res = await fetchWithAuth("/api/elein/events-multimodal/multimodal/generate-voice-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead_name: voiceLeadName,
          company: voiceCompany,
          title: voiceTitle,
          tone: voiceTone,
          custom_pain_point: customPainPoint
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "AI Voice Note Script Generator",
          minTier: "PRO",
          description: "Synthesize high-converting conversational audio drops and voice scripts."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        setGeneratedScript(data.script);
        setEstimatedDuration(data.estimated_duration_sec);
        toast.success(`Synthesized ${data.estimated_duration_sec}s voice script for ${voiceLeadName}!`);
      } else {
        const err = await res.json().catch(() => ({ detail: "Voice generation failed." }));
        toast.error(err.detail || "Failed to generate voice script.");
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error generating voice script.");
    } finally {
      setIsGeneratingVoice(false);
    }
  };

  // Synthesize Video Prospecting Card
  const handleGenerateVideoCard = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Video Prospecting Loom Studio",
        minTier: "PRO",
        description: "Generate personalized dynamic video teardown cards with customized animated thumbnail copy."
      });
      return;
    }
    setIsGeneratingVideo(true);
    try {
      const res = await fetchWithAuth("/api/elein/events-multimodal/multimodal/generate-video-card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead_name: videoLeadName,
          company: videoCompany,
          video_topic: videoTopic
        })
      });
      if (res.status === 402) {
        openPaywall({
          featureName: "Video Prospecting Loom Studio",
          minTier: "PRO",
          description: "Generate personalized dynamic video teardown cards with customized animated thumbnail copy."
        });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        setGeneratedVideoCard(data);
        toast.success("Generated personalized video card preview!");
      } else {
        const err = await res.json().catch(() => ({ detail: "Video generation failed." }));
        toast.error(err.detail || "Failed to generate video card.");
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error generating video card.");
    } finally {
      setIsGeneratingVideo(false);
    }
  };

  // Filter Attendees by Seniority
  const filteredAttendees = attendees.filter(a => {
    if (seniorityFilter === "all") return true;
    return a.seniority === seniorityFilter;
  });

  const enrollableFiltered = filteredAttendees.filter(a => a.status !== 'enrolled');
  const isAllFilteredSelected = enrollableFiltered.length > 0 && enrollableFiltered.every(a => selectedAttendeeIds.has(a.id));

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-hidden animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="event-multimodal-studio-title"
    >
      <div className="relative w-full max-w-5xl h-[90dvh] max-h-[90dvh] rounded-xl border border-border bg-card text-card-foreground shadow-2xl flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <h2 id="event-multimodal-studio-title" className="text-base font-semibold text-foreground">LinkedIn Event Harvester & Multimodal Voice Studio</h2>
              {!isPro && (
                <button
                  onClick={() => openPaywall({
                    featureName: "LinkedIn Event Harvester & Multimodal Studio",
                    minTier: "PRO",
                    description: "Upgrade to Pro to harvest attendees from LinkedIn events and synthesize voice notes & video cards."
                  })}
                  className="px-2 py-0.5 rounded-md bg-muted/40 text-[10px] font-medium text-foreground border border-border hover:bg-muted transition-all cursor-pointer"
                >
                  PRO
                </button>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Harvest event attendees and generate conversational audio notes and video cards.
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close dialog"
              className="rounded-lg p-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Global Telemetry Bar with Disclosed Benchmarks */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 px-6 py-3 border-b border-border bg-muted/40 text-xs shrink-0">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Attendees In Pool:</span>
            <span className="font-semibold text-foreground">{attendees.length} leads</span>
          </div>
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Event Acceptance Lift:</span>
            <span className="font-semibold text-foreground">+64%</span>
            <span className="text-[10px] rounded bg-background px-1.5 py-0.2 text-muted-foreground border border-border">Benchmark</span>
          </div>
          <div className="flex items-center gap-2">
            <Volume2 className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Voice Note Reply:</span>
            <span className="font-semibold text-foreground">38.4%</span>
            <span className="text-[10px] rounded bg-background px-1.5 py-0.2 text-muted-foreground border border-border">Benchmark</span>
          </div>
          <div className="flex items-center gap-2">
            <Film className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Video Card CTR:</span>
            <span className="font-semibold text-foreground">52.1%</span>
            <span className="text-[10px] rounded bg-background px-1.5 py-0.2 text-muted-foreground border border-border">Benchmark</span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div role="tablist" aria-label="Studio mode navigation" className="flex border-b border-border px-6 bg-background overflow-x-auto shrink-0">
          <button
            role="tab"
            aria-selected={activeTab === 'events'}
            onClick={() => setActiveTab('events')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'events'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Users className="h-4 w-4" />
            LinkedIn Event Harvester
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'voice'}
            onClick={() => setActiveTab('voice')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'voice'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Mic className="h-4 w-4" />
            Voice Note Studio (30s Audio Drops)
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'video'}
            onClick={() => setActiveTab('video')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'video'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Video className="h-4 w-4" />
            Dynamic Loom Video Cards
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'library'}
            onClick={() => setActiveTab('library')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'library'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Layers className="h-4 w-4" />
            Multimodal Asset Library
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: EVENT & GROUP HARVESTER */}
          {activeTab === 'events' && (
            <div className="space-y-6">
              {/* Harvester Input Card */}
              <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-3">
                <div className="text-xs font-semibold text-foreground">Harvest Registered Event / Group Attendees</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">LinkedIn Event or Group URL</label>
                    <input
                      type="text"
                      value={eventUrl}
                      onChange={(e) => setEventUrl(e.target.value)}
                      placeholder="https://www.linkedin.com/events/..."
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Event / Webinar Label</label>
                    <input
                      type="text"
                      value={eventName}
                      onChange={(e) => setEventName(e.target.value)}
                      placeholder="B2B AI Summit 2026"
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={handleExportAttendeesCsv}
                    disabled={isExportingAttendees || attendees.length === 0}
                    className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground hover:bg-muted transition-all disabled:opacity-50 cursor-pointer"
                  >
                    <Download className={`h-3.5 w-3.5 ${isExportingAttendees ? 'animate-spin' : ''}`} />
                    <span>Export CSV</span>
                  </button>
                  <button
                    onClick={handleHarvestEvent}
                    disabled={isHarvesting}
                    className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${isHarvesting ? 'animate-spin' : ''}`} />
                    <span>Harvest Attendees</span>
                  </button>
                </div>
              </div>

              {/* Seniority Filter & Batch Action Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Filter className="h-3.5 w-3.5" /> Filter Seniority:
                  </span>
                  {[
                    { id: "all", label: "All" },
                    { id: "c_level", label: "C-Level" },
                    { id: "vp", label: "VP" },
                    { id: "director", label: "Director" }
                  ].map((f) => (
                    <button
                      key={f.id}
                      onClick={() => setSeniorityFilter(f.id)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                        seniorityFilter === f.id
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted/40 border border-border text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleToggleSelectAll}
                    className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  >
                    {isAllFilteredSelected ? (
                      <>
                        <CheckSquare className="h-3.5 w-3.5 text-foreground" />
                        <span>Deselect Filtered ({enrollableFiltered.length})</span>
                      </>
                    ) : (
                      <>
                        <Square className="h-3.5 w-3.5" />
                        <span>Select Filtered ({enrollableFiltered.length})</span>
                      </>
                    )}
                  </button>
                  <button
                    onClick={handleBatchEnroll}
                    disabled={isEnrollingBatch || selectedAttendeeIds.size === 0}
                    className="flex items-center gap-2 rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    <Rocket className="h-3.5 w-3.5" />
                    <span>Enroll Selected ({selectedAttendeeIds.size})</span>
                  </button>
                </div>
              </div>

              {/* Attendees List */}
              <div className="grid grid-cols-1 gap-3">
                {filteredAttendees.map((att) => {
                  const isSelected = selectedAttendeeIds.has(att.id);
                  const isEnrolled = att.status === 'enrolled';
                  const isExpanded = expandedIcebreakerIds.has(att.id);

                  return (
                    <div
                      key={att.id}
                      className={`rounded-lg border p-3.5 transition-all ${
                        isEnrolled
                          ? 'border-border bg-muted/40'
                          : isSelected
                          ? 'border-foreground bg-muted/20'
                          : 'border-border bg-card hover:bg-muted/20'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3 flex-1">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            disabled={isEnrolled}
                            onChange={() => toggleAttendeeSelection(att.id)}
                            className="mt-1 rounded border-border bg-background text-primary focus:ring-0 cursor-pointer"
                          />
                          <div className="space-y-1.5 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-xs text-foreground">{att.prospect_name}</span>
                              <span className="text-xs text-muted-foreground">- {att.title} @ {att.company_name}</span>
                              {att.linkedin_url && (
                                <a
                                  href={att.linkedin_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-0.5"
                                  title="View LinkedIn Profile"
                                >
                                  <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                              <span className="rounded px-1.5 py-0.5 text-[10px] font-medium uppercase bg-muted/40 text-foreground border border-border">
                                {(att.seniority || 'member').replace('_', ' ')}
                              </span>
                            </div>

                            {/* Contextual Event Icebreaker */}
                            <div className="rounded-lg bg-muted/40 p-2.5 text-xs text-foreground font-mono border border-border flex items-start justify-between gap-2">
                              <div className="flex-1">
                                <p className={isExpanded ? "whitespace-pre-wrap leading-relaxed" : "line-clamp-2 leading-relaxed"}>
                                  "{att.generated_icebreaker}"
                                </p>
                                {att.generated_icebreaker && att.generated_icebreaker.length > 90 && (
                                  <button
                                    type="button"
                                    onClick={() => toggleExpandIcebreaker(att.id)}
                                    className="text-[10px] text-muted-foreground hover:text-foreground font-sans mt-1 underline cursor-pointer"
                                  >
                                    {isExpanded ? "Show less" : "Show full icebreaker"}
                                  </button>
                                )}
                              </div>
                              <button
                                type="button"
                                onClick={() => {
                                  navigator.clipboard.writeText(att.generated_icebreaker);
                                  setCopiedIcebreakerId(att.id);
                                  toast.success("Copied icebreaker!");
                                  setTimeout(() => setCopiedIcebreakerId(null), 2000);
                                }}
                                className="ml-2 text-muted-foreground hover:text-foreground shrink-0 cursor-pointer p-1"
                                title="Copy icebreaker"
                                aria-label="Copy icebreaker"
                              >
                                {copiedIcebreakerId === att.id ? (
                                  <Check className="h-3.5 w-3.5 text-foreground" />
                                ) : (
                                  <Copy className="h-3.5 w-3.5" />
                                )}
                              </button>
                            </div>
                          </div>
                        </div>

                        {/* Status */}
                        <div className="shrink-0 pt-1">
                          {isEnrolled ? (
                            <span className="flex items-center gap-1 text-[11px] font-medium text-foreground">
                              <CheckCircle2 className="h-3.5 w-3.5" /> Enrolled
                            </span>
                          ) : (
                            <span className="text-[11px] text-muted-foreground">Ready</span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 2: VOICE NOTE STUDIO */}
          {activeTab === 'voice' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Voice Form Config */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-foreground">Conversational Voice Note Parameters</div>
                  <button
                    onClick={() => handleExportAssetsCsv('voice_script')}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  >
                    <Download className="h-3.5 w-3.5" /> Export Audio Scripts CSV
                  </button>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Prospect Name</label>
                    <input
                      type="text"
                      value={voiceLeadName}
                      onChange={(e) => setVoiceLeadName(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Company</label>
                    <input
                      type="text"
                      value={voiceCompany}
                      onChange={(e) => setVoiceCompany(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Tone & Delivery Style</label>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { id: "casual_peer", label: "Casual Peer" },
                        { id: "executive_brief", label: "Executive Brief" },
                        { id: "provocative_observation", label: "Provocative" }
                      ].map((t) => (
                        <button
                          key={t.id}
                          onClick={() => setVoiceTone(t.id as any)}
                          className={`p-2 rounded-lg text-xs font-medium border text-center transition-all cursor-pointer ${
                            voiceTone === t.id
                              ? 'border-foreground bg-muted text-foreground'
                              : 'border-border bg-background text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Custom Pain Point</label>
                    <input
                      type="text"
                      value={customPainPoint}
                      onChange={(e) => setCustomPainPoint(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <button
                    onClick={handleGenerateVoiceScript}
                    disabled={isGeneratingVoice}
                    className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    <Mic className={`h-3.5 w-3.5 ${isGeneratingVoice ? 'animate-spin' : ''}`} />
                    <span>Synthesize 30s Audio Script</span>
                    <span className="rounded bg-primary-foreground/20 px-1.5 py-0.5 text-[10px] font-mono">2 Credits</span>
                  </button>
                </div>
              </div>

              {/* Generated Audio Card Preview */}
              <div className="rounded-lg border border-border bg-muted/40 p-5 flex flex-col justify-between space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                      <Volume2 className="h-4 w-4 text-muted-foreground" /> Synthesized Audio Drop
                    </span>
                    <span className="rounded-md bg-background px-2 py-0.5 text-xs font-mono font-medium text-foreground border border-border">
                      ~{estimatedDuration}s Duration
                    </span>
                  </div>

                  {/* Simulated Audio Waveform Bar with Web Speech API integration */}
                  <div className="rounded-lg bg-background p-4 border border-border flex items-center gap-4">
                    <button
                      type="button"
                      onClick={handleToggleAudio}
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground hover:bg-primary/90 transition-all cursor-pointer shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      title={isPlayingAudio ? "Pause speech simulation" : "Listen to speech simulation"}
                      aria-label={isPlayingAudio ? "Pause speech simulation" : "Listen to speech simulation"}
                    >
                      {isPlayingAudio ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
                    </button>
                    <div className="flex-1 flex items-center gap-1 h-6">
                      {[40, 75, 30, 90, 60, 45, 80, 100, 70, 50, 85, 40, 65, 95, 35, 55, 75, 45].map((h, i) => (
                        <div
                          key={i}
                          className={`flex-1 rounded-full transition-all ${
                            isPlayingAudio ? 'bg-foreground animate-pulse' : 'bg-muted-foreground/60 dark:bg-muted-foreground/40'
                          }`}
                          style={{ height: isPlayingAudio ? `${Math.min(100, h * 1.2)}%` : `${h}%` }}
                        />
                      ))}
                    </div>
                  </div>

                  {/* Teleprompter Script */}
                  <div className="space-y-1.5">
                    <div className="text-[11px] text-muted-foreground font-medium">Spoken Teleprompter Script:</div>
                    <div className="rounded-lg bg-background p-3.5 text-xs text-foreground leading-relaxed font-mono border border-border whitespace-pre-wrap">
                      {(generatedScript || '').split('[pause]').map((chunk, idx, arr) => (
                        <React.Fragment key={idx}>
                          {chunk}
                          {idx < arr.length - 1 && (
                            <span className="inline-block mx-1 rounded bg-muted px-1 py-0.5 text-[10px] font-sans font-medium text-foreground border border-border">
                              PAUSE 0.5s
                            </span>
                          )}
                        </React.Fragment>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(generatedScript);
                      setCopiedVoiceScript(true);
                      toast.success("Voice script copied to clipboard!");
                      setTimeout(() => setCopiedVoiceScript(false), 2000);
                    }}
                    className="flex-1 flex items-center justify-center gap-2 rounded-lg border border-border bg-card py-2 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
                  >
                    {copiedVoiceScript ? (
                      <>
                        <Check className="h-4 w-4 text-foreground" />
                        Copied to Clipboard!
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4" />
                        Copy Script for Voice Note
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab('library');
                      toast.info("Viewing generated voice scripts in Asset Library.");
                    }}
                    className="px-3 py-2 rounded-lg border border-border bg-card text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer flex items-center gap-1.5"
                    title="View in Asset Library"
                  >
                    <Layers className="h-3.5 w-3.5" />
                    <span>View in Library</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: DYNAMIC LOOM VIDEO CARDS */}
          {activeTab === 'video' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Video Form Config */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-foreground">Video Prospecting Card Parameters</div>
                  <button
                    onClick={() => handleExportAssetsCsv('video_card')}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  >
                    <Download className="h-3.5 w-3.5" /> Export Video Cards CSV
                  </button>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Prospect Name</label>
                    <input
                      type="text"
                      value={videoLeadName}
                      onChange={(e) => setVideoLeadName(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Company</label>
                    <input
                      type="text"
                      value={videoCompany}
                      onChange={(e) => setVideoCompany(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground block mb-1">Teardown Topic</label>
                    <input
                      type="text"
                      value={videoTopic}
                      onChange={(e) => setVideoTopic(e.target.value)}
                      placeholder="60s Outbound Pipeline Audit"
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <button
                    onClick={handleGenerateVideoCard}
                    disabled={isGeneratingVideo}
                    className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    <Film className={`h-3.5 w-3.5 ${isGeneratingVideo ? 'animate-spin' : ''}`} />
                    <span>Generate Video Card Preview</span>
                    <span className="rounded bg-primary-foreground/20 px-1.5 py-0.5 text-[10px] font-mono">3 Credits</span>
                  </button>
                </div>
              </div>

              {/* Video Card Preview */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-foreground">Live LinkedIn DM Card Preview:</div>
                <div className="rounded-lg border border-border bg-card overflow-hidden">
                  {/* Thumbnail Banner */}
                  <div className="relative aspect-video bg-muted/40 flex flex-col items-center justify-center p-6 text-center border-b border-border">
                    <button
                      type="button"
                      aria-label="Play video preview"
                      onClick={() => {
                        if (generatedVideoCard?.video_url) {
                          window.open(generatedVideoCard.video_url, '_blank', 'noopener,noreferrer');
                        }
                      }}
                      className="flex h-12 w-12 items-center justify-center rounded-full bg-background border border-border text-foreground mb-3 cursor-pointer hover:bg-muted transition-colors shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <Play className="h-5 w-5 ml-0.5" />
                    </button>
                    <div className="text-sm font-semibold text-foreground tracking-tight max-w-xs">
                      {generatedVideoCard?.thumbnail_title || "Custom Video Teardown"}
                    </div>
                    <span className="absolute bottom-3 right-3 rounded bg-background border border-border px-2 py-0.5 text-[10px] font-mono text-muted-foreground">
                      ~{generatedVideoCard?.estimated_duration_sec || 58}s
                    </span>
                  </div>

                  {/* DM Copy Box */}
                  <div className="p-4 space-y-3">
                    <p className="text-xs text-foreground font-mono bg-muted/40 p-2.5 rounded-lg border border-border">
                      "{generatedVideoCard?.dm_copy || "Personalized video teardown available."}"
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          if (generatedVideoCard?.dm_copy) {
                            navigator.clipboard.writeText(generatedVideoCard.dm_copy);
                            setCopiedVideoDm(true);
                            toast.success("Copied video message with link!");
                            setTimeout(() => setCopiedVideoDm(false), 2000);
                          }
                        }}
                        className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-background hover:bg-muted py-2 text-xs font-medium text-foreground border border-border transition-colors cursor-pointer"
                      >
                        {copiedVideoDm ? (
                          <>
                            <Check className="h-4 w-4 text-foreground" />
                            Copied DM Copy!
                          </>
                        ) : (
                          <>
                            <Copy className="h-4 w-4" />
                            Copy Video DM with Link
                          </>
                        )}
                      </button>
                      {generatedVideoCard?.video_url && (
                        <a
                          href={generatedVideoCard.video_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 px-3 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                          title="Open video URL in new tab"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: MULTIMODAL ASSET LIBRARY */}
          {activeTab === 'library' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Filter Assets:</span>
                  {(['all', 'voice_script', 'video_card'] as const).map(type => (
                    <button
                      key={type}
                      onClick={() => setLibraryFilter(type)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                        libraryFilter === type
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted/40 border border-border text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {type === 'all' ? 'All Assets' : type === 'voice_script' ? 'Voice Scripts' : 'Video Cards'}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => handleExportAssetsCsv(libraryFilter === 'all' ? undefined : libraryFilter)}
                  className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>Export Library CSV</span>
                </button>
              </div>

              {isLoadingAssets ? (
                <div className="flex items-center justify-center py-12 text-muted-foreground text-xs">
                  <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                  Loading multimodal assets...
                </div>
              ) : savedAssets.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground text-xs border border-dashed border-border rounded-lg">
                  No multimodal assets saved yet. Synthesize your first voice drop or video card above!
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {savedAssets.map(asset => (
                    <div key={asset.id} className="rounded-lg border border-border bg-card p-3.5 space-y-2 flex flex-col justify-between">
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="rounded px-1.5 py-0.5 text-[10px] font-medium uppercase bg-muted/40 text-foreground border border-border">
                            {asset.asset_type === 'voice_script' ? 'Voice Script' : 'Video Card'}
                          </span>
                          <span className="text-[11px] text-muted-foreground font-mono">
                            ~{asset.estimated_duration_sec}s
                          </span>
                        </div>
                        {asset.thumbnail_text && (
                          <div className="text-xs font-semibold text-foreground">
                            {asset.thumbnail_text}
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground line-clamp-3 font-mono">
                          {asset.script_text}
                        </p>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-border">
                        <button
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(asset.script_text);
                            toast.success("Copied asset content!");
                          }}
                          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer"
                        >
                          <Copy className="h-3 w-3" /> Copy
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteAsset(asset.id)}
                          className="flex items-center gap-1 text-[11px] text-destructive hover:text-destructive/80 transition-colors cursor-pointer"
                          title="Delete asset"
                        >
                          <Trash2 className="h-3 w-3" /> Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-6 py-4 bg-muted/40 shrink-0">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <ShieldAlert className="h-4 w-4 text-muted-foreground" />
            Paranoia Active: Video assets strictly signed and bounded to prevent link decay.
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="rounded-lg border border-border bg-background px-4 py-2 text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              Close Studio
            </button>
          )}
        </div>

      </div>
    </div>
  );
}
