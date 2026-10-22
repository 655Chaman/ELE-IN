// ORCHESTRATOR: This file coordinates state only. Do NOT add UI rendering here. Add new UI sections as separate components in components/knowledge/

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { 
  BrainCircuit, Users, ShieldAlert, 
  UploadCloud, Link as LinkIcon, FileText, 
  Search, Plus, Trash2, Edit2, Play, MessageSquare, Sparkles, X, Database, RefreshCw,
  Lock, Zap, ArrowRight, Cpu
} from "lucide-react";

import { usePaywall } from "@/contexts/PaywallContext";


import { AddUrlModal } from "@/components/knowledge/AddUrlModal";
import { UploadPdfModal } from "@/components/knowledge/UploadPdfModal";
import { KnowledgeAssetList } from "@/components/knowledge/KnowledgeAssetList";
import { TestDriveSimulator } from "@/components/knowledge/TestDriveSimulator";
import { SynthesisEditor } from "@/components/knowledge/SynthesisEditor";
import { PersonaManager } from "@/components/knowledge/PersonaManager";
import { BayesianIcpView } from "@/components/knowledge/BayesianIcpView";
import { AIGatewayView } from "@/components/knowledge/AIGatewayView";
import { ReusableConfirmDialog } from "@/components/ReusableConfirmDialog";
import { ElesiumLogo } from "@/components/ElesiumLogo";

import { toast } from "sonner";
import { fetchWithAuth } from "@/lib/apiClient";
import useSWR from "swr";
import { supabase } from "@/lib/supabase";
const fetcher = (url: string) => fetchWithAuth(url).then(async r => {
  if (!r.ok) {
    let msg = "Error";
    try { const data = await r.json(); msg = data.detail || msg; } catch(e) {}
    throw new Error(msg);
  }
  return r.json();
});

interface Objection {
  id: string;
  name: string;
  keywords?: string;
  rebuttal: string;
}

interface Persona {
  id: string;
  name: string;
  pain_points: string;
  value_prop: string;
  tone_tweaks: string;
}

export default function EleInKnowledge() {
  const { data: assets, error: assetsError, mutate: mutateAssets, isLoading: isAssetsLoading } = useSWR("/api/assets/knowledge/assets", fetcher, {
    revalidateOnFocus: false
  });
  const { data: synthesis, mutate: mutateSynthesis, isLoading: isSynthesisLoading } = useSWR("/api/assets/knowledge/synthesis", fetcher, {
    revalidateOnFocus: false
  });
  const { data: personas, mutate: mutatePersonas, isLoading: isPersonasLoading } = useSWR("/api/knowledge/personas", fetcher);
  const { data: objections, mutate: mutateObjections, isLoading: isObjectionsLoading } = useSWR("/api/assets/knowledge/objections", fetcher);
  const { data: workspace, mutate: mutateWorkspace } = useSWR("/api/elein/workspaces/me", fetcher);
  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>("/api/elein/workspaces/billing", fetcher);




  useEffect(() => {
    if (!workspace?.id) return;

    const channel = supabase.channel(`knowledge-realtime-${workspace.id}`)
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'knowledge_assets',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        () => {
          mutateAssets();
        }
      )
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'knowledge_synthesis',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        () => {
          mutateSynthesis();
        }
      )
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'knowledge_synthesis_drafts',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        () => {
          mutateSynthesis();
        }
      )
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'personas',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        () => {
          mutatePersonas();
        }
      )
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'knowledge_objections',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        () => {
          mutateObjections();
        }
      )
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'objections',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        () => {
          mutateObjections();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [workspace?.id, mutateAssets, mutateSynthesis, mutatePersonas, mutateObjections]);

  // Editable company name state (inline in the page header)
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedCompanyName, setEditedCompanyName] = useState("");
  useEffect(() => {
    if (workspace?.name && !isEditingName) {
      setEditedCompanyName(workspace.name);
    }
  }, [workspace]);

  const [isSavingCompanyName, setIsSavingCompanyName] = useState(false);

  const handleSaveCompanyName = async () => {
    if (!editedCompanyName.trim()) return;
    setIsSavingCompanyName(true);
    try {
      const res = await fetchWithAuth("/api/elein/workspaces/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editedCompanyName.trim() })
      });
      if (!res.ok) throw new Error("Failed to save");
      toast.success("Company name updated!");
      setIsEditingName(false);
      mutateWorkspace();
    } catch {
      toast.error("Failed to save company name.");
    } finally {
      setIsSavingCompanyName(false);
    }
  };

  const [activeTab, setActiveTab] = useState("assets");
  
  const [deletingAssetId, setDeletingAssetId] = useState<string | null>(null);
  const [retryingAssetId, setRetryingAssetId] = useState<string | null>(null);

  // Paste Text State
  const [isSavingPaste, setIsSavingPaste] = useState(false);
  const [isPasteModalOpen, setIsPasteModalOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pasteTitle, setPasteTitle] = useState("");




  const [isDeleting, setIsDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);




  const [isCreatingObjection, setIsCreatingObjection] = useState(false);

  const handleAddObjection = async () => {
    setIsCreatingObjection(true);
    const tempObjection = { 
      id: 'temp-' + Date.now(), 
      name: "New Objection", 
      keywords: "",
      rebuttal: "New Playbook",
      created_at: new Date().toISOString() 
    };
    mutateObjections((current: any[]) => [...(current || []), tempObjection], false);

    try {
      const res = await fetchWithAuth("/api/assets/knowledge/objections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trigger: "New Objection", playbook: "New Playbook" })
      });
      if (res.ok) {
        const newObj = await res.json();
        toast.success("Objection created!");
        mutatePersonas(); mutateObjections();
        setSelectedObjection(newObj);
      } else {
        mutateObjections();
        toast.error("Failed to create objection");
      }
    } catch (e) {
      mutateObjections();
      toast.error("Error creating objection");
    } finally {
      setIsCreatingObjection(false);
    }
  };

  const [pendingSelectObjection, setPendingSelectObjection] = useState<any>(null);

  const handleDiscardAndSelect = () => {
    if (pendingSelectObjection) {
      setSelectedObjection(pendingSelectObjection);
      setIsDirtyObjection(false);
      if (window.innerWidth < 1024) {
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
      }
      setPendingSelectObjection(null);
    }
  };

  const [objectionToDelete, setObjectionToDelete] = useState<string | null>(null);

  const handleDeleteObjection = (id: string) => {
    setObjectionToDelete(id);
  };

  const confirmDeleteObjection = async () => {
    if (!objectionToDelete) return;
    const id = objectionToDelete;
    setObjectionToDelete(null);
    try {
      const res = await fetchWithAuth(`/api/assets/knowledge/objections/${id}`, { method: "DELETE" });
      if (res.ok) {
        toast.success("Objection deleted!");
        mutatePersonas(); mutateObjections();
        if (selectedObjection?.id === id) {
          setSelectedObjection(null);
          setIsDirtyObjection(false);
        }
      }
    } catch (e) {
      toast.error("Error deleting objection");
    }
  };

  const [isDocOpen, setIsDocOpen] = useState(false);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isDocOpen) setIsDocOpen(false);
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isDocOpen]);

  
  const [selectedObjection, setSelectedObjection] = useState<Objection | null>(null);
  const [isDirtyObjection, setIsDirtyObjection] = useState(false);
  const [isSavingObjection, setIsSavingObjection] = useState(false);

  

  
  const handleDeleteAsset = (id: string) => {
    setDeletingAssetId(id);
  };

  const confirmDeleteAsset = async () => {
    if (!deletingAssetId) return;
    setIsDeleting(true);
    try {
      const res = await fetchWithAuth(`/api/assets/knowledge/assets/${deletingAssetId}`, { method: "DELETE" });
      if (res.ok) {
        toast.success("Asset deleted!");
        mutateAssets(); 
        mutateSynthesis();
        setDeletingAssetId(null);
      } else {
        toast.error("Failed to delete asset");
      }
    } catch (e) {
      toast.error("Error deleting asset");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleRetryAsset = async (id: string) => {
    setRetryingAssetId(id);
    try {
      const res = await fetchWithAuth(`/api/assets/knowledge/assets/${id}/retry`, { method: "POST" });
      if (!res.ok) throw new Error("Retry failed");
      toast.success("Retrying asset processing...");
      mutateAssets();
    } catch (e: any) {
      toast.error(e.message || "Failed to retry asset");
    } finally {
      setRetryingAssetId(null);
    }
  };

  const handlePasteText = async () => {
    if (isAssetCapped) {
      openPaywall({ featureName: "Knowledge Base Storage" });
      toast.info(`Free plan limit reached (${assetCount}/${maxAssets} documents). Upgrade to Growth Pro to add up to 25 documents.`);
      return;
    }
    if (!pasteText.trim()) return toast.error("Please enter some text");
    if (!pasteTitle.trim()) return toast.error("Please enter a title");
    
    try {
      setIsSavingPaste(true);
      const res = await fetchWithAuth("/api/assets/knowledge/upload/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: pasteTitle, text: pasteText })
      });
      if (!res.ok) {
         let errText = "Failed to upload text";
         try {
             const data = await res.json();
             errText = data.detail || errText;
         } catch(err) {}
         throw new Error(errText);
      }
      await res.json();
      toast.success("Text saved! Processing in background...");
      setPasteText("");
      setPasteTitle("");
      setIsPasteModalOpen(false);
      mutateAssets();
      mutateSynthesis();
    } catch (e: any) {
      toast.error(e.message || "Failed to upload text");
    } finally {
      setIsSavingPaste(false);
    }
  };

  
  const assetCount = Array.isArray(assets) ? assets.length : 0;
  const personaCount = Array.isArray(personas) ? personas.length : 0;
  const objectionCount = Array.isArray(objections) ? objections.length : 0;

  const tier = billingData?.tier || "FREE";
  const isPro = tier === "PRO" || tier === "ENTERPRISE";
  const maxAssets = isPro ? (tier === "ENTERPRISE" ? 100 : 25) : 3;
  const maxPersonas = isPro ? (tier === "ENTERPRISE" ? 50 : 10) : 1;
  const isAssetCapped = !isPro && assetCount >= maxAssets;
  const isPersonaCapped = !isPro && personaCount >= maxPersonas;

  const tabs = [
    { id: 'assets', label: "Company Info", icon: <Database size={13} />, count: `${assetCount}` },
    { id: 'personas', label: "Buyer Personas", icon: <Users size={13} />, count: `${personaCount}` },
    { id: 'objections', label: "Objection Playbook", icon: <ShieldAlert size={13} />, count: `${objectionCount}` },
    { id: 'bayesian_icp', label: "Lead Fit AI", icon: <Sparkles size={13} />, count: isPro ? "Active" : "Pro" },
    { id: 'ai_gateway', label: "AI Models & BYOK", icon: <ElesiumLogo size={13} />, count: isPro ? "Active" : "Pro" },
  ];

  const docsContext: Record<string, {
    name: string;
    badge: string;
    what: string;
    why: string;
    roi: string;
  }> = {
    assets: {
      name: "Company Knowledge Sources",
      badge: "Context Foundation",
      what: "Your company's single source of truth—including websites, pitch decks, case studies, and internal battlecards.",
      why: "Default AI hallucinates and sends generic sales templates that get ignored or marked as spam. Grounding the AI in your real materials ensures every message cites your actual features, customer case studies, and proven metrics.",
      roi: "Stops wasting outreach limits and credits on generic emails that get 0% reply rates. Hyper-personalized outreach citing real ROI turns more cold leads into booked meetings."
    },
    personas: {
      name: "Buyer Personas",
      badge: "Targeted Messaging",
      what: "Target profiles defining specific job titles, seniority levels, and daily departmental pain points.",
      why: "A VP of Engineering deletes emails about quota attainment; a CFO deletes emails about technical refactors. Personas instruct the AI on who reads each message so it speaks their exact language.",
      roi: "Speaking directly to a prospect's daily pain points increases positive reply rates by 3x–4x. You book significantly more meetings from the same pool of outreach credits."
    },
    objections: {
      name: "Objection Playbooks",
      badge: "Deal Rescue",
      what: "Battle-tested counterarguments for common prospect pushbacks ('Too expensive', 'No budget', 'Using competitor').",
      why: "Standard AI is naturally polite and apologizes when rejected, ending the conversation and losing the deal. Playbooks teach the AI how to handle hesitation like a seasoned enterprise Account Executive.",
      roi: "Rescues deals you already paid credits to acquire. Converting even 1 out of 5 hesitations into a discovery call doubles your campaign ROI without buying more lead lists."
    },
    bayesian_icp: {
      name: "Lead Fit AI (Smart Lead Qualification)",
      badge: "Credit Protection",
      what: "An auto-learning lead filter that scores prospect buying probability from 0 to 100 before any outreach is sent.",
      why: "Never blast messages to leads who will never buy. As you book meetings, the AI automatically learns which job titles, company sizes, and industries convert best and prioritizes them.",
      roi: "The Credit Protection Gate holds low-scoring leads, preventing you from burning monthly credits and LinkedIn limits on cold prospects with zero buying intent."
    },
    ai_gateway: {
      name: "AI Models & Cost Control (BYOK)",
      badge: "Infrastructure",
      what: "Compute telemetry, model routing, and direct Bring-Your-Own-Key provider vault.",
      why: "Match model intelligence to deal value—use fast, economical models for initial connection requests, and deep-reasoning models (DeepSeek-R1) for complex enterprise objection handling.",
      roi: "Connect your own OpenAI, Anthropic, or DeepSeek API keys to pay raw wholesale provider pricing with 0% platform markup, saving up to 80% on high-volume runs."
    }
  };


  const activeDocData = docsContext[activeTab];

  return (
    <div className="min-h-[100dvh] bg-background text-foreground font-sans overflow-x-hidden">
      <main className="max-w-[1200px] mx-auto p-6 md:p-8 lg:p-10">

        
        {/* ─── HEADER ─────────────────────────────────────────────── */}
        <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            {/* Editable company name title */}
            {isEditingName ? (
              <div className="flex items-center gap-3 mb-1.5">
                <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/50 flex items-center justify-center text-foreground/80 shrink-0">
                  <BrainCircuit className="w-4 h-4" />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    disabled={isSavingCompanyName}
                    value={editedCompanyName}
                    onChange={(e) => setEditedCompanyName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveCompanyName(); if (e.key === 'Escape') setIsEditingName(false); }}
                    placeholder="Workspace Name"
                    className="text-lg font-medium bg-background border border-border/70 rounded-lg px-2.5 py-1 text-foreground focus:outline-none focus:border-foreground/40 w-auto min-w-[200px]"
                  />
                  <button 
                    type="button"
                    onClick={handleSaveCompanyName} 
                    disabled={isSavingCompanyName}
                    className="text-xs px-3 py-1 bg-foreground text-background rounded-md font-medium hover:bg-foreground/90 disabled:opacity-50 flex items-center justify-center min-w-[48px] transition-colors cursor-pointer"
                  >
                    {isSavingCompanyName ? <div className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" /> : 'Save'}
                  </button>
                  <button 
                    type="button"
                    onClick={() => setIsEditingName(false)} 
                    disabled={isSavingCompanyName}
                    className="text-xs px-2.5 py-1 bg-muted text-muted-foreground rounded-md hover:bg-muted/80 disabled:opacity-50 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <h1
                role="button"
                tabIndex={0}
                onClick={() => setIsEditingName(true)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setIsEditingName(true);
                  }
                }}
                title="Click to rename"
                className="text-xl font-medium tracking-tight text-foreground mb-1 flex w-fit items-center gap-2.5 cursor-pointer group focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-md"
              >
                <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/50 flex items-center justify-center text-foreground/80 shrink-0">
                  <BrainCircuit className="w-4 h-4" />
                </div>
                <span className="hover:text-foreground/80 transition-colors">
                  {workspace?.name ? `${workspace.name}'s Knowledge Base` : 'Knowledge Base'}
                </span>
                <Edit2 size={13} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity ml-1" />
              </h1>
            )}
            <p className="text-xs text-muted-foreground">
              Ground your AI on your real business so every credit sent turns into high-converting, personalized outreach.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Minimalist Readiness Badge */}
            <div className="h-8.5 flex items-center gap-2 px-3 rounded-lg border border-border/50 bg-card/60 text-xs">
              <span className={`w-1.5 h-1.5 rounded-full ${
                assetCount > 0 && personaCount > 0 ? 'bg-emerald-500' : 'bg-amber-500/80'
              }`} />
              <span className="text-xs text-foreground/90 font-medium">
                {assetCount > 0 && personaCount > 0 ? 'AI Memory: Calibrated' : 'Needs Sources'}
              </span>
            </div>

            {/* Subtle Plan / Quota Indicator */}
            {!isPro && (
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Knowledge Base & AI Brain Capacity" })}
                className="h-8.5 flex items-center gap-1.5 px-3 rounded-lg border border-border/50 bg-card/60 hover:bg-muted text-xs text-muted-foreground hover:text-foreground font-medium transition-colors cursor-pointer"
                title="Manage AI Capacity"
              >
                <span>Free Plan · {assetCount}/{maxAssets} sources</span>
                {(isAssetCapped || isPersonaCapped) && (
                  <span className="text-amber-500 ml-1 font-semibold">· Quota Reached</span>
                )}
              </button>
            )}

            <button
              type="button"
              onClick={() => setIsDocOpen(true)}
              className="h-8.5 flex items-center gap-1.5 px-3 rounded-lg border border-border/50 bg-card/60 hover:bg-muted text-xs text-muted-foreground hover:text-foreground font-medium transition-colors cursor-pointer"
            >
              <FileText size={13} />
              <span>Guide</span>
            </button>

            <TestDriveSimulator />
          </div>
        </div>

        {/* Value Explainer Strip */}
        <div className="mb-6 p-3.5 px-4 rounded-xl border border-border/50 bg-card/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2.5 text-muted-foreground">
            <Sparkles size={13} className="text-foreground/80 shrink-0" />
            <span><strong className="text-foreground font-medium">Why train your AI?</strong> Without context, AI sends generic templates that get ignored. Grounding your AI ensures every message cites your real proof points, handles objections, and protects outreach credits.</span>
          </div>
          <button
            type="button"
            onClick={() => setIsDocOpen(true)}
            className="text-foreground/80 hover:text-foreground text-[11px] font-medium underline underline-offset-4 shrink-0 self-start sm:self-auto cursor-pointer"
          >
            How it works →
          </button>
        </div>

        {/* ─── TAB NAVIGATION ───── */}
        <div 
          role="tablist"
          aria-label="Knowledge Base Navigation"
          className="flex items-center gap-6 border-b border-border mb-8 overflow-x-auto scrollbar-none"
        >
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            const isProBadge = tab.count === 'Pro';
            const isActiveBadge = tab.count === 'Active';

            return (
              <button 
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`group relative flex items-center gap-2 pb-3 pt-1 text-xs font-medium transition-colors cursor-pointer whitespace-nowrap border-b-2 -mb-px outline-hidden ${
                  isActive 
                    ? 'border-foreground text-foreground' 
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                }`}
              >
                <span className={`shrink-0 transition-colors ${isActive ? 'text-foreground' : 'text-muted-foreground group-hover:text-foreground'}`}>
                  {tab.icon}
                </span>
                <span>{tab.label}</span>
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-full leading-none transition-colors ${
                  isProBadge
                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-medium'
                    : isActiveBadge
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-medium'
                    : isActive
                    ? 'bg-muted text-foreground font-medium'
                    : 'bg-muted/60 text-muted-foreground group-hover:text-foreground'
                }`}>
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        {/* ─── CONTENT AREA ────────────────────────────────────────────────────────── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -10, filter: 'blur(4px)' }}
            transition={{ duration: 0.3 }}
          >
            {activeTab === 'assets' && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Data Sources (Spans 2 columns) */}
                <div className="lg:col-span-2 group outline-none">
                  <div className="h-full bg-card/40 border border-border/50 rounded-xl p-6 lg:p-7 overflow-hidden relative">
                    <div className="relative z-10">
                      {/* Section heading */}
                      <div className="flex items-center gap-3 mb-6">
                        <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shadow-2xs">
                          <Database className="w-4 h-4 text-foreground/80" />
                        </div>
                        <div>
                          <h3 className="text-sm font-medium tracking-tight text-foreground">
                            Company Knowledge Sources
                          </h3>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Ground your AI on your website, decks, and case studies so outreach cites real ROI and proof points.
                          </p>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 mb-8">

                        {/* ── 1. Upload PDF ── */}
                        <UploadPdfModal mutateAssets={mutateAssets} />

                        {/* ── 2. Scrape Website ── */}
                        <AddUrlModal mutateAssets={mutateAssets} />

                        {/* ── 3. Paste Text ── */}
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => {
                            if (isAssetCapped) {
                              openPaywall({ featureName: "Knowledge Base Storage" });
                              toast.info(`Free plan limit reached (${assetCount}/${maxAssets} documents). Upgrade to Growth Pro to add up to 25 documents.`);
                            } else {
                              setIsPasteModalOpen(true);
                            }
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              if (isAssetCapped) {
                                openPaywall({ featureName: "Knowledge Base Storage" });
                              } else {
                                setIsPasteModalOpen(true);
                              }
                            }
                          }}
                          className="border border-border/50 bg-card/40 hover:bg-card/70 hover:border-border/80 transition-all rounded-xl p-5 flex flex-col justify-between min-h-[200px] cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          <div>
                            <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 mb-3">
                              {isAssetCapped ? <Lock size={15} className="text-amber-500" /> : <FileText size={15} />}
                            </div>
                            <h3 className="font-medium text-sm text-foreground">
                              {isAssetCapped ? "Paste Notes" : "Paste Notes"}
                            </h3>
                            <p className="text-xs text-muted-foreground mt-1 mb-3 leading-relaxed">
                              {isAssetCapped
                                ? `Plan limit reached (${assetCount}/${maxAssets} docs)`
                                : "Paste raw positioning, email snippets, or internal FAQs."}
                            </p>
                          </div>
                          <button 
                            type="button"
                            tabIndex={-1}
                            className={`w-full py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5 border cursor-pointer ${
                              isAssetCapped
                                ? "border-border/60 bg-muted/40 text-muted-foreground hover:bg-muted/60"
                                : "border-border/70 bg-background/60 hover:bg-muted/60 text-foreground"
                            }`}
                          >
                            {isAssetCapped ? (
                              <>
                                <Lock size={12} className="text-amber-500" />
                                <span>Quota Reached</span>
                              </>
                            ) : (
                              <span>Open Editor</span>
                            )}
                          </button>
                        </div>
                      </div>

                      <div className="pt-6 border-t border-border/40">
                        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
                          Connected Knowledge Sources ({assetCount})
                        </h4>
                        {(!assets && !assetsError) ? (
                          <div className="space-y-2">
                            {[1,2,3].map(i => <div key={i} className="h-12 w-full bg-muted/30 rounded-lg animate-pulse" />)}
                          </div>
                        ) : (
                          <KnowledgeAssetList 
                            assets={Array.isArray(assets) ? assets : []} 
                            onDelete={handleDeleteAsset} 
                            onRetry={handleRetryAsset}
                            mutateAssets={mutateAssets}
                            mutateSynthesis={mutateSynthesis}
                          />
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                <SynthesisEditor synthesis={synthesis} mutateSynthesis={mutateSynthesis} />

              </div>
            )}

            {activeTab === 'personas' && (
              isPersonasLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 p-4">
                  {[1,2,3].map(i => <div key={i} className="h-48 w-full bg-muted/40 rounded-xl animate-pulse" />)}
                </div>
              ) : (
                <PersonaManager personas={personas} mutatePersonas={mutatePersonas} mutateObjections={mutateObjections} />
              )
            )}

{activeTab === 'objections' && (
              <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4 min-h-[580px]">
                {/* LEFT SIDEBAR: "Battle Playbooks" */}
                <div className="bg-card/40 border border-border/50 rounded-xl flex flex-col overflow-hidden">
                  <div className="p-4 border-b border-border/40 flex justify-between items-center bg-card/60">
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80">
                        <ShieldAlert className="w-3.5 h-3.5" />
                      </div>
                      <div>
                        <h3 className="text-xs font-medium text-foreground tracking-tight">Battle Playbooks</h3>
                        <p className="text-[11px] text-muted-foreground">
                          {Array.isArray(objections) ? objections.length : 0} playbook{(Array.isArray(objections) ? objections.length : 0) === 1 ? '' : 's'}
                        </p>
                      </div>
                    </div>
                    <button 
                      type="button"
                      onClick={handleAddObjection} 
                      disabled={isCreatingObjection} 
                      className="bg-foreground text-background hover:bg-foreground/90 rounded-lg px-2.5 py-1 text-xs font-medium flex items-center gap-1 disabled:opacity-50 transition-colors shadow-2xs cursor-pointer"
                    >
                      {isCreatingObjection ? <div className="w-3 h-3 rounded-full border-2 border-background border-t-transparent animate-spin" /> : <Plus size={13} />}
                      <span>New</span>
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
                    {isObjectionsLoading ? (
                      [1,2,3,4].map(i => <div key={i} className="h-14 w-full bg-muted/30 rounded-lg animate-pulse" />)
                    ) : (
                      (Array.isArray(objections) ? objections : []).length === 0 ? (
                        <div className="flex flex-col items-center justify-center flex-1 py-12 px-3 text-center h-full">
                          <div className="w-9 h-9 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center mb-2.5 text-muted-foreground">
                            <ShieldAlert className="w-4 h-4" />
                          </div>
                          <p className="text-xs font-medium text-foreground mb-1">No playbooks yet</p>
                          <p className="text-[11px] text-muted-foreground mb-3 leading-relaxed">Train the AI on how to counter pushbacks.</p>
                          <button 
                            type="button"
                            onClick={handleAddObjection} 
                            disabled={isCreatingObjection} 
                            className="px-3 py-1.5 bg-foreground text-background hover:bg-foreground/90 rounded-lg text-xs font-medium transition-colors shadow-2xs cursor-pointer"
                          >
                            {isCreatingObjection ? <div className="w-3.5 h-3.5 rounded-full border-2 border-background border-t-transparent animate-spin" /> : 'Create Playbook'}
                          </button>
                        </div>
                      ) : (
                        (Array.isArray(objections) ? objections : []).map((obj: any) => (
                          <div
                            key={obj.id}
                            role="button"
                            tabIndex={0}
                            onClick={() => {
                              if (isDirtyObjection && selectedObjection?.id !== obj.id) {
                                setPendingSelectObjection(obj);
                                return;
                              }
                              setSelectedObjection(obj); setIsDirtyObjection(false); 
                              if (window.innerWidth < 1024) {
                                window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                              }
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                if (isDirtyObjection && selectedObjection?.id !== obj.id) {
                                  setPendingSelectObjection(obj);
                                  return;
                                }
                                setSelectedObjection(obj);
                                setIsDirtyObjection(false);
                              }
                            }}
                            className={`group p-3 rounded-lg cursor-pointer transition-all border text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                              selectedObjection?.id === obj.id
                                ? 'bg-card border-border text-foreground shadow-2xs'
                                : 'border-transparent hover:bg-muted/40 text-muted-foreground hover:text-foreground'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-1.5">
                                  {selectedObjection?.id === obj.id && (
                                    <span className="w-1.5 h-1.5 rounded-full bg-foreground shrink-0" />
                                  )}
                                  <p className="text-xs font-medium text-foreground truncate">{obj.name || 'Untitled Objection'}</p>
                                </div>
                                <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{obj.rebuttal?.substring(0, 50) || 'No strategy defined'}...</p>
                              </div>
                              <button
                                type="button"
                                aria-label="Delete playbook"
                                onClick={(e) => { e.stopPropagation(); handleDeleteObjection(obj.id); }}
                                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive shrink-0 cursor-pointer"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        ))
                      )
                    )}
                  </div>
                </div>
                
                {/* RIGHT PANEL: The Playbook Editor */}
                <div className="bg-card/40 border border-border/50 rounded-xl shadow-2xs overflow-hidden flex flex-col">
                  {selectedObjection ? (
                    <div className="flex-1 flex flex-col">
                      {/* Status bar */}
                      <div className="px-5 py-2.5 border-b border-border/40 flex items-center gap-2 bg-muted/10 text-xs">
                        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Editing</span>
                        <span className="text-border">/</span>
                        <span className="text-xs font-medium text-foreground truncate">{selectedObjection.name || 'Untitled'}</span>
                      </div>

                      <div className="p-5 flex flex-col gap-4 flex-1 overflow-y-auto">
                        {/* Trigger Phrase Card */}
                        <div className="bg-card/60 border border-border/50 rounded-lg p-3.5">
                          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5 block">Trigger Phrase</label>
                          <input 
                            type="text" 
                            maxLength={500}
                            disabled={isSavingObjection}
                            className="w-full bg-transparent text-sm font-medium text-foreground focus:outline-none placeholder:text-muted-foreground/50 disabled:opacity-50"
                            value={selectedObjection.name || ''}
                            onChange={(e) => {
                              setSelectedObjection({...selectedObjection, name: e.target.value});
                              setIsDirtyObjection(true);
                            }}
                            placeholder="When prospect says (e.g. 'We don't have budget')..."
                          />
                        </div>

                        {/* AI Response Strategy Card */}
                        <div className="flex-1 bg-card/60 border border-border/50 rounded-lg p-3.5 flex flex-col">
                          <div className="flex justify-between items-center mb-2">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                              <ElesiumLogo size={12} />
                              AI Response Strategy
                            </label>
                          </div>
                          <textarea 
                            maxLength={5000}
                            disabled={isSavingObjection}
                            className="flex-1 w-full bg-transparent text-xs focus:outline-none resize-none leading-relaxed text-foreground placeholder:text-muted-foreground/50 disabled:opacity-50 min-h-[220px]"
                            value={selectedObjection.rebuttal || ''}
                            onChange={(e) => {
                              setSelectedObjection({...selectedObjection, rebuttal: e.target.value});
                              setIsDirtyObjection(true);
                            }}
                            placeholder="Instructions for the AI on how to handle this objection, key counterarguments, and pivot language..."
                          />
                          
                          <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/40">
                            <p className="text-[11px] text-muted-foreground">
                              Be specific. Provide exact wording and proof points to challenge hesitation politely.
                            </p>
                            <div className={`text-[10px] font-mono ${(selectedObjection.rebuttal?.length || 0) > 4800 ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
                              {selectedObjection.rebuttal?.length || 0}/5000
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="p-3.5 border-t border-border/40 flex justify-between items-center bg-card/40 mt-auto">
                        <button 
                          type="button"
                          onClick={() => handleDeleteObjection(selectedObjection.id)}
                          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
                        >
                          <Trash2 size={13} /> Delete
                        </button>

                        <button 
                          type="button"
                          disabled={!isDirtyObjection || isSavingObjection}
                          onClick={async () => {
                            if (!selectedObjection) return;
                            mutateObjections(
                              (current: any[]) => current?.map(p => p.id === selectedObjection.id ? { ...p, ...selectedObjection } : p) || [],
                              false
                            );
                            setIsDirtyObjection(false);
                            setIsSavingObjection(true);
                            try {
                              const res = await fetchWithAuth(`/api/assets/knowledge/objections/${selectedObjection.id}`, {
                                method: "PUT",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                  trigger: selectedObjection.name || 'Untitled',
                                  playbook: selectedObjection.rebuttal || ''
                                })
                              });
                              if (res.ok) {
                                toast.success("Playbook updated successfully");
                                mutateObjections();
                              } else {
                                mutateObjections();
                                toast.error("Failed to update playbook");
                                setIsDirtyObjection(true); 
                              }
                            } catch (e) {
                              mutateObjections();
                              toast.error("Error updating playbook");
                              setIsDirtyObjection(true); 
                            } finally {
                              setIsSavingObjection(false);
                            }
                          }}
                          className={`px-4 py-1.5 text-xs font-medium rounded-lg transition-all shadow-2xs cursor-pointer ${
                            isDirtyObjection || isSavingObjection
                              ? 'bg-foreground text-background hover:bg-foreground/90' 
                              : 'bg-muted/50 text-muted-foreground cursor-not-allowed'
                          } disabled:opacity-50`}
                        >
                          {isSavingObjection ? <div className="w-3.5 h-3.5 rounded-full border-2 border-background border-t-transparent animate-spin" /> : 'Save Strategy'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full p-8 text-center flex-1">
                      <div className="w-10 h-10 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center mb-3 text-muted-foreground">
                        <ShieldAlert className="w-5 h-5" />
                      </div>
                      
                      <h3 className="text-sm font-medium text-foreground mb-1">Select a Battle Playbook</h3>
                      <p className="text-xs text-muted-foreground max-w-sm leading-relaxed mb-5">
                        Each playbook trains the AI to handle a specific objection your prospects raise — turning pushback into booked meetings.
                      </p>
                      
                      <div className="flex flex-wrap gap-2 justify-center max-w-sm mb-6">
                        {['Too expensive', 'Wrong timing', 'Using competitor'].map((ex) => (
                          <span key={ex} className="px-2.5 py-1 rounded-md bg-muted/30 border border-border/40 text-[11px] text-muted-foreground font-medium">
                            {ex}
                          </span>
                        ))}
                      </div>
                      
                      {(Array.isArray(objections) ? objections : []).length === 0 && (
                        <button
                          type="button"
                          onClick={handleAddObjection}
                          disabled={isCreatingObjection}
                          className="px-3.5 py-1.5 bg-foreground text-background hover:bg-foreground/90 rounded-lg text-xs font-medium transition-all shadow-2xs flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                        >
                          {isCreatingObjection ? <div className="w-3.5 h-3.5 rounded-full border-2 border-background border-t-transparent animate-spin" /> : <Plus size={13} />}
                          Create First Playbook
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'bayesian_icp' && (
              <BayesianIcpView />
            )}

            {activeTab === 'ai_gateway' && (
              <AIGatewayView isPro={isPro} />
            )}
          </motion.div>
        </AnimatePresence>

      </main>

      {/* DYNAMIC DOCUMENTATION MODAL */}
      <AnimatePresence>
        {isDocOpen && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-background/80 backdrop-blur-sm cursor-pointer"
              onClick={() => setIsDocOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              className="relative w-full max-w-lg bg-card border border-border/60 rounded-xl shadow-2xl overflow-hidden flex flex-col"
            >
              <div className="px-5 py-4 border-b border-border/50 flex justify-between items-center bg-card">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 bg-muted/60 border border-border/40 rounded-lg flex items-center justify-center text-foreground/80">
                    <FileText size={14} />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-foreground">{activeDocData?.name || "Documentation"}</h3>
                    <p className="text-[10px] text-muted-foreground">AI Knowledge Guide</p>
                  </div>
                </div>
                <button 
                  type="button"
                  aria-label="Close documentation"
                  onClick={() => setIsDocOpen(false)}
                  className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <X size={15} />
                </button>
              </div>

              <div className="p-5 space-y-3.5 flex-1 overflow-y-auto text-xs leading-relaxed">
                <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground font-medium">
                      What It Is
                    </span>
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/40 font-mono">
                      {activeDocData?.badge}
                    </span>
                  </div>
                  <p className="text-foreground font-medium text-xs pt-0.5">
                    {activeDocData?.what}
                  </p>
                </div>

                <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground font-medium block">
                    Why Use This Feature?
                  </span>
                  <p className="text-muted-foreground text-xs leading-relaxed">
                    {activeDocData?.why}
                  </p>
                </div>

                <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground font-medium block">
                    Why Spend Credits &amp; ROI
                  </span>
                  <p className="text-muted-foreground text-xs leading-relaxed">
                    {activeDocData?.roi}
                  </p>
                </div>
              </div>

              <div className="px-5 py-3 bg-muted/20 border-t border-border/50 flex justify-end">
                <button 
                  type="button"
                  onClick={() => setIsDocOpen(false)}
                  className="px-3.5 py-1.5 bg-foreground text-background rounded-lg text-xs font-medium hover:bg-foreground/90 transition-all shadow-2xs cursor-pointer"
                >
                  Close
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* PASTE TEXT MODAL */}
      <AnimatePresence>
        {isPasteModalOpen && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="absolute inset-0 bg-background/80 backdrop-blur-sm cursor-pointer"
              onClick={() => setIsPasteModalOpen(false)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              className="relative bg-card border border-border/60 shadow-2xl rounded-xl w-full max-w-md p-5 overflow-hidden flex flex-col"
            >
              <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80">
                    <FileText size={13} />
                  </div>
                  <h3 className="text-sm font-medium text-foreground">Paste Knowledge</h3>
                </div>
                <button 
                  type="button"
                  aria-label="Close"
                  onClick={() => setIsPasteModalOpen(false)} 
                  className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground rounded-md hover:bg-muted transition-colors cursor-pointer"
                >
                  <X size={15} />
                </button>
              </div>
              <input 
                type="text" 
                value={pasteTitle} 
                onChange={e => setPasteTitle(e.target.value)} 
                placeholder="Title (e.g. Competitor Battlecard)" 
                className="w-full bg-background border border-border/60 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-border text-foreground mb-3 placeholder:text-muted-foreground/60" 
              />
              <textarea 
                value={pasteText} 
                onChange={e => setPasteText(e.target.value)} 
                placeholder="Paste your raw text, emails, or internal positioning notes..." 
                className="w-full bg-background border border-border/60 rounded-lg px-3 py-2.5 text-xs focus:outline-none focus:border-border min-h-[160px] mb-4 resize-none text-foreground placeholder:text-muted-foreground/60 leading-relaxed" 
              />
              <div className="flex gap-2 w-full justify-end">
                <button 
                  type="button"
                  onClick={() => setIsPasteModalOpen(false)} 
                  className="px-3.5 py-1.5 rounded-lg border border-border/60 text-muted-foreground hover:text-foreground hover:bg-muted text-xs font-medium transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={handlePasteText} 
                  disabled={isSavingPaste}
                  className="px-4 py-1.5 rounded-lg bg-foreground text-background hover:bg-foreground/90 text-xs font-medium transition-colors shadow-2xs disabled:opacity-50 flex items-center justify-center cursor-pointer"
                >
                  {isSavingPaste ? (
                    <div className="w-3.5 h-3.5 rounded-full border-2 border-background border-t-transparent animate-spin" />
                  ) : (
                    'Save Text'
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* DELETE ASSET CONFIRMATION MODAL */}
      <AnimatePresence>
        {deletingAssetId && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="absolute inset-0 bg-background/80 backdrop-blur-sm cursor-pointer"
              onClick={() => !isDeleting && setDeletingAssetId(null)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              className="relative bg-card border border-border/60 shadow-2xl rounded-xl w-full max-w-sm p-5 overflow-hidden text-center"
            >
              <div className="w-8 h-8 rounded-lg bg-destructive/10 text-destructive flex items-center justify-center mb-3 mx-auto">
                <Trash2 size={16} />
              </div>
              <h3 className="text-sm font-medium text-foreground mb-1">Delete Knowledge Asset</h3>
              <p className="text-xs text-muted-foreground mb-5 leading-relaxed">
                Are you sure you want to delete this asset? The AI will immediately lose context derived from it.
              </p>
              <div className="flex gap-2 w-full justify-end">
                <button 
                  type="button"
                  onClick={() => setDeletingAssetId(null)}
                  disabled={isDeleting}
                  className="flex-1 px-3 py-1.5 rounded-lg border border-border/60 text-muted-foreground hover:text-foreground text-xs font-medium hover:bg-muted transition-colors disabled:opacity-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={confirmDeleteAsset}
                  disabled={isDeleting}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-destructive text-destructive-foreground text-xs font-medium hover:bg-destructive/90 transition-colors shadow-2xs disabled:opacity-50 cursor-pointer"
                >
                  {isDeleting ? "Deleting..." : "Delete"}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <ReusableConfirmDialog
        isOpen={!!objectionToDelete}
        title="Delete Playbook"
        description="Are you sure you want to delete this playbook? This cannot be undone."
        confirmLabel="Delete Playbook"
        onConfirm={confirmDeleteObjection}
        onCancel={() => setObjectionToDelete(null)}
      />

      <ReusableConfirmDialog
        isOpen={!!pendingSelectObjection}
        title="Discard Changes"
        description="Your unsaved changes will be lost. Are you sure you want to discard them?"
        confirmLabel="Discard Changes"
        onConfirm={handleDiscardAndSelect}
        onCancel={() => setPendingSelectObjection(null)}
      />
    </div>
  )
}