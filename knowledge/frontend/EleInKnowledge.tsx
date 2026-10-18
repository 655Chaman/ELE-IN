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

import ShinyText from "@/components/ShinyText";
import StarBorder from "@/components/StarBorder";
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

    const channel = supabase.channel('knowledge-assets-changes')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'knowledge_assets',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        (payload: any) => {
          mutateAssets();
          if (payload?.new?.status === 'synced' || payload?.new?.status === 'completed') {
            mutateSynthesis();
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [workspace?.id, mutateAssets, mutateSynthesis]);

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
    { id: 'assets', label: "Company Info", icon: <Database size={14} />, count: `${assetCount}/${maxAssets}` },
    { id: 'personas', label: "Buyer Personas", icon: <Users size={14} />, count: `${personaCount}/${maxPersonas}` },
    { id: 'objections', label: "Objection Playbook", icon: <ShieldAlert size={14} />, count: `${objectionCount}` },
    { id: 'bayesian_icp', label: "Bayesian ICP", icon: <Sparkles size={14} className="text-indigo-400" />, count: isPro ? "Active" : "Pro" },
    { id: 'ai_gateway', label: "AI Gateway & BYOK", icon: <ElesiumLogo size={14} />, count: isPro ? "Active" : "Pro" },
  ];


  const docsContext: Record<string, any> = {
    assets: {
      name: "Data Sources",
      icon: <Database className="w-6 h-6" />,
      content: "Large Language Models possess a vast understanding of the internet, but they do not know the unique specifics of your company. By providing your foundational assets—such as raw sales decks, PDF case studies, and live website URLs—you ground the AI in your reality. This prevents hallucinations and generic sales-speak. When a prospect asks detailed questions about your features, the AI can instantly cite specific case studies and prove ROI, converting friction directly into booked meetings.",
      color: "from-blue-500 to-indigo-500"
    },
    personas: {
      name: "Buyer Personas",
      icon: <Users className="w-6 h-6" />,
      content: "Detailed profiles of your target audience are critical. A VP of Sales cares about quota attainment, while a Head of RevOps focuses on tool consolidation and data silos. By defining the exact personas you are targeting, you instruct the AI on who it is talking to. It will automatically adjust its tone and map your product's value directly to the unique, daily pain points of the person reading the email.",
      color: "from-blue-600 to-cyan-500"
    },
    objections: {
      name: "Objection Playbook",
      icon: <ShieldAlert className="w-6 h-6" />,
      content: "AI is naturally agreeable and polite. If a prospect replies 'We use a competitor' or 'We don't have budget', a default AI might simply apologize and end the conversation. Your Objection Playbook explicitly trains the AI on your battle-tested counters. It learns to politely challenge the prospect and pivot the conversation—turning hesitant replies into booked meetings by handling friction exactly like your best senior Account Executive would.",
      color: "from-orange-500 to-red-500"
    },
    bayesian_icp: {
      name: "Bayesian ICP Learning",
      icon: <Sparkles className="w-6 h-6 text-indigo-400" />,
      content: "Static ICP definitions become obsolete quickly. Ele-in's Bayesian ICP module maintains a live Beta-distribution prior across all firmographic and behavioral signals (headcount, funding, title seniority, and activity). Every positive conversion incrementally increases signal alpha, while lost opportunities increase beta. This produces mathematically grounded qualification scores rather than hallucinated LLM guesses.",
      color: "from-indigo-500 to-blue-500"
    },
    ai_gateway: {
      name: "AI Gateway & BYOK",
      icon: <ElesiumLogo size={22} />,
      content: "High-volume outbound requires reliable, cost-effective reasoning infrastructure. The AI Gateway coordinates model selection across specialized NIM reasoning endpoints (DeepSeek-R1, Nemotron-4 340B, and Llama 3.2), provides granular token consumption auditing, and lets Growth Pro teams connect zero-markup Bring-Your-Own-Key provider vaults.",
      color: "from-blue-600 to-indigo-500"
    }
  };


  const activeDocData = docsContext[activeTab];

  return (
    <div className="min-h-[100dvh] bg-background text-foreground font-sans overflow-x-hidden">
      <main className="max-w-[1200px] mx-auto p-6 md:p-8 lg:p-10">

        
        {/* ─── HEADER ─────────────────────────────────────────────── */}
        <div className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            {/* Editable company name title */}
            {isEditingName ? (
              <div className="flex items-center gap-3 mb-2">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20 shrink-0">
                  <BrainCircuit className="w-4 h-4 text-primary" />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    disabled={isSavingCompanyName}
                    value={editedCompanyName}
                    onChange={(e) => setEditedCompanyName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveCompanyName(); if (e.key === 'Escape') setIsEditingName(false); }}
                    placeholder="Workspace Name"
                    className="text-xl font-bold bg-background border border-border focus:border-primary rounded-lg px-2.5 py-1 text-foreground focus:outline-none w-auto min-w-[220px] shadow-xs disabled:opacity-50"
                  />
                  <button 
                    type="button"
                    onClick={handleSaveCompanyName} 
                    disabled={isSavingCompanyName}
                    className="text-xs px-3 py-1.5 bg-primary text-primary-foreground rounded-lg font-semibold hover:bg-primary/90 disabled:opacity-50 flex items-center justify-center min-w-[50px] transition-colors cursor-pointer"
                  >
                    {isSavingCompanyName ? <div className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" /> : 'Save'}
                  </button>
                  <button 
                    type="button"
                    onClick={() => setIsEditingName(false)} 
                    disabled={isSavingCompanyName}
                    className="text-xs px-3 py-1.5 bg-muted text-muted-foreground rounded-lg hover:bg-muted/80 disabled:opacity-50 transition-colors cursor-pointer"
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
                className="text-2xl font-bold tracking-tight text-foreground mb-2 flex w-fit items-center gap-3 cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
              >
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
                  <BrainCircuit className="w-4 h-4 text-primary" />
                </div>
                <span className="group-hover:text-primary transition-colors">
                  {workspace?.name ? `${workspace.name}'s Knowledge Base` : 'Your Knowledge Base'}
                </span>
                <Edit2 size={14} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </h1>
            )}
            <p className="text-sm text-muted-foreground max-w-lg">
              This is where your AI learns about your company. The more you add here, the smarter and more accurate your outreach becomes — no generic emails, ever.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {/* Knowledge Readiness Badge (Transcript 2: Goal Gradient Feedback) */}
            <div className="h-9 flex items-center gap-2 px-3 py-2 rounded-lg border border-border/60 bg-muted/20 backdrop-blur-md shadow-2xs">
              <span className={`w-2 h-2 rounded-full ${
                assetCount > 0 && personaCount > 0 ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
              }`} />
              <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <ElesiumLogo size={13} />
                AI Brain: {assetCount > 0 && personaCount > 0 ? 'Grounded & Ready' : `${assetCount > 0 || personaCount > 0 ? 'Partially Grounded' : 'Needs Knowledge'}`}
              </span>
            </div>

            <button
              type="button"
              onClick={() => setIsDocOpen(true)}
              className="h-9 flex items-center gap-2 px-4 py-2 bg-muted/30 border border-border/60 rounded-lg text-xs font-semibold hover:bg-muted/50 text-foreground transition-colors cursor-pointer"
            >
              <FileText size={14} /> How it works
            </button>
            <TestDriveSimulator />
          </div>
        </div>

        {/* ─── IN-SITU PAY RAMP: KNOWLEDGE BASE & AI BRAIN CAPACITY ─── */}
        {!isPro && (
          <div className="mb-8 p-4 sm:p-5 rounded-xl bg-gradient-to-r from-primary/10 via-primary/5 to-transparent border border-primary/20 shadow-xs relative overflow-hidden flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-start sm:items-center gap-3.5">
              <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0 text-primary">
                <ElesiumLogo size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                    Free AI Knowledge Plan
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20">
                    {assetCount}/{maxAssets} Docs &bull; {personaCount}/{maxPersonas} Personas
                  </span>
                  {(isAssetCapped || isPersonaCapped) && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/20 flex items-center gap-1">
                      <Lock size={10} /> Quota Limit Reached
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-1 max-w-xl">
                  Growth Pro unlocks <strong>25 Knowledge Assets</strong>, up to <strong>10 Target Buyer Personas</strong>, and the <strong>Continuous Bayesian ICP Machine Learning Engine</strong>.
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => openPaywall({ featureName: "Knowledge Base & AI Brain Capacity" })}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground shadow-xs transition-all cursor-pointer whitespace-nowrap self-start md:self-auto shrink-0"
            >
              <span>Expand AI Capacity</span>
              <ArrowRight size={14} />
            </button>
          </div>
        )}

        {/* ─── PILL NAVIGATION WITH LIVE COUNTS ───── */}
        <div 
          role="tablist"
          aria-label="Knowledge Base Navigation"
          className="bg-muted/40 p-1.5 rounded-xl border border-border/60 w-full flex flex-wrap lg:flex-nowrap items-center gap-1.5 mb-8 shadow-2xs"
        >
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button 
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex-1 min-w-[140px] flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-lg text-xs font-semibold transition-all duration-200 cursor-pointer ${isActive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/30'}`}
              >
                {isActive && (
                  <motion.div layoutId="kb-active-pill" className="absolute inset-0 bg-background shadow-xs border border-border/50 rounded-lg" transition={{ type: "spring", bounce: 0.15, duration: 0.4 }} />
                )}
                <span className="relative z-10 flex items-center justify-center gap-2">
                  {tab.icon} <span>{tab.label}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-bold font-mono transition-colors ${
                    isActive ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'
                  }`}>
                    {tab.count}
                  </span>
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
                  <div className="h-full bg-card border border-border/60 rounded-xl p-6 lg:p-8 overflow-hidden relative shadow-xs">
                    <div className="relative z-10">
                      {/* Section heading */}
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-10 h-10 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-xs">
                          <Database className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="text-xl font-semibold tracking-tight text-foreground flex items-center gap-2">
                            Tell <ElesiumLogo size={18} /> AI about your company
                          </h3>
                          <p className="text-xs text-muted-foreground mt-0.5">Add anything — your website, a sales deck, your pitch, notes. The AI reads it all.</p>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8 mt-6">

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
                          className="border border-border/60 bg-muted/20 hover:bg-muted/30 transition-all rounded-xl p-5 flex flex-col justify-between cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <div>
                            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary mb-2">
                              {isAssetCapped ? <Lock size={18} className="text-amber-500" /> : <FileText size={18} />}
                            </div>
                            <h3 className="font-semibold text-sm text-foreground">
                              {isAssetCapped ? "Upgrade to Paste Text" : "Copy-paste anything"}
                            </h3>
                            <p className="text-xs text-muted-foreground mt-1 mb-3">
                              {isAssetCapped
                                ? `Limit reached (${assetCount}/${maxAssets} docs)`
                                : "Paste raw text, email templates, or notes directly."}
                            </p>
                          </div>
                          <button 
                            type="button"
                            tabIndex={-1}
                            className={`w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 shadow-xs cursor-pointer ${
                              isAssetCapped
                                ? "bg-muted text-foreground border border-border hover:bg-muted/80"
                                : "bg-primary text-primary-foreground hover:bg-primary/90"
                            }`}
                          >
                            {isAssetCapped ? (
                              <>
                                <Lock size={12} className="text-amber-500" />
                                <span>Unlock More Docs</span>
                              </>
                            ) : (
                              <span>Open Editor</span>
                            )}
                          </button>
                        </div>
                      </div>

                      <div className="pt-6 border-t border-border/60">
                        <h4 className="text-sm font-semibold mb-1 text-foreground flex items-center gap-1.5">
                          What <ElesiumLogo size={14} /> AI has learned so far
                        </h4>
                        <p className="text-xs text-muted-foreground mb-4">Each item below is part of your AI's memory. Delete any that are outdated.</p>
                        {(!assets && !assetsError) ? (
                          <div className="space-y-3">
                            {[1,2,3].map(i => <div key={i} className="h-16 w-full bg-muted/40 rounded-lg animate-pulse" />)}
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
              <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 min-h-[680px]">
                {/* LEFT SIDEBAR: "Battle Playbooks" */}
                <div className="bg-card border border-border/60 rounded-xl flex flex-col shadow-xs overflow-hidden relative">
                  <div className="relative z-10 flex flex-col h-full">
                    <div className="p-5 border-b border-border/60 flex justify-between items-start">
                      <div className="flex flex-col">
                        <span className="inline-block px-2 py-0.5 rounded-md bg-red-500/10 text-red-600 dark:text-red-400 text-[10px] font-bold uppercase tracking-wider mb-2 w-fit border border-red-500/20">Objection Engine</span>
                        <h3 className="text-lg font-bold text-foreground">Battle Playbooks</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {Array.isArray(objections) ? objections.length : 0} playbook{(Array.isArray(objections) ? objections.length : 0) === 1 ? '' : 's'} trained
                        </p>
                      </div>
                      <button 
                        type="button"
                        onClick={handleAddObjection} 
                        disabled={isCreatingObjection} 
                        className="bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg px-3 py-1.5 text-xs font-semibold flex items-center gap-1.5 disabled:opacity-50 transition-colors shadow-xs cursor-pointer"
                      >
                        {isCreatingObjection ? <div className="w-3.5 h-3.5 rounded-full border-2 border-primary-foreground border-t-transparent animate-spin" /> : <Plus size={14} />}
                        <span className="hidden sm:inline">New Playbook</span>
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-2">
                      {isObjectionsLoading ? (
                        [1,2,3,4].map(i => <div key={i} className="h-16 w-full bg-muted/40 rounded-lg animate-pulse" />)
                      ) : (
                        (Array.isArray(objections) ? objections : []).length === 0 ? (
                          <div className="flex flex-col items-center justify-center flex-1 py-12 text-center h-full">
                            <div className="w-12 h-12 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-3">
                              <ShieldAlert className="w-6 h-6 text-red-400" />
                            </div>
                            <p className="text-sm font-medium text-foreground mb-1">No playbooks yet</p>
                            <p className="text-xs text-muted-foreground mb-4 px-4">Create your first objection handler to train the AI on how to respond to pushback.</p>
                            <button 
                              type="button"
                              onClick={handleAddObjection} 
                              disabled={isCreatingObjection} 
                              className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-colors flex items-center justify-center min-w-[140px] shadow-xs cursor-pointer"
                            >
                              {isCreatingObjection ? <div className="w-4 h-4 rounded-full border-2 border-primary-foreground border-t-transparent animate-spin" /> : 'Create First Playbook'}
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
                              className={`group p-3.5 rounded-lg cursor-pointer transition-all border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                                selectedObjection?.id === obj.id
                                  ? 'bg-red-500/10 border-red-500/30 shadow-xs'
                                  : 'border-transparent hover:bg-muted/40 hover:border-border/60'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-semibold text-foreground truncate">{obj.name || 'Untitled Objection'}</p>
                                  <p className="text-xs text-muted-foreground mt-0.5 truncate">{obj.rebuttal?.substring(0, 60) || 'No strategy yet'}...</p>
                                </div>
                                <button
                                  type="button"
                                  aria-label="Delete playbook"
                                  onClick={(e) => { e.stopPropagation(); handleDeleteObjection(obj.id); }}
                                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive shrink-0 mt-0.5"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                              {selectedObjection?.id === obj.id && (
                                <div className="mt-2 flex items-center gap-1.5">
                                  <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
                                  <span className="text-[10px] font-bold text-red-500 uppercase tracking-wider">Active</span>
                                </div>
                              )}
                            </div>
                          ))
                        )
                      )}
                    </div>
                  </div>
                </div>
                
                {/* RIGHT PANEL: The Playbook Editor */}
                <div className="bg-card border border-border/60 rounded-xl shadow-xs overflow-hidden flex flex-col relative">
                  {selectedObjection ? (
                    <div className="flex-1 flex flex-col relative z-10">
                      {/* Status bar */}
                      <div className="px-6 py-3 border-b border-border/60 flex items-center gap-3 bg-muted/20">
                        <div className="flex items-center gap-1.5">
                          <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                          <span className="text-[10px] font-bold text-red-500 uppercase tracking-wider">Editing Playbook</span>
                        </div>
                        <span className="text-border">/</span>
                        <span className="text-xs font-medium text-muted-foreground truncate">{selectedObjection.name || 'Untitled'}</span>
                      </div>

                      <div className="p-6 md:p-8 flex flex-col gap-6 flex-1 overflow-y-auto">
                        {/* Trigger Phrase Card */}
                        <div className="bg-muted/20 border border-border/60 rounded-lg p-5 shadow-xs">
                          <label className="text-[10px] font-bold text-red-500/80 dark:text-red-400/80 uppercase tracking-widest mb-3 block">Trigger Phrase</label>
                          <input 
                            type="text" 
                            maxLength={500}
                            disabled={isSavingObjection}
                            className="w-full bg-transparent text-xl font-bold text-foreground focus:outline-none placeholder:text-muted-foreground/50 disabled:opacity-50"
                            value={selectedObjection.name || ''}
                            onChange={(e) => {
                              setSelectedObjection({...selectedObjection, name: e.target.value});
                              setIsDirtyObjection(true);
                            }}
                            placeholder="When prospect says..."
                          />
                        </div>

                        {/* AI Response Strategy Card */}
                        <div className="flex-1 bg-background border border-border/60 rounded-lg p-5 flex flex-col shadow-xs">
                          <div className="flex justify-between items-center mb-3">
                            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5">
                              <ElesiumLogo size={12} />
                              AI Response Strategy
                            </label>
                          </div>
                          <textarea 
                            maxLength={5000}
                            disabled={isSavingObjection}
                            className="flex-1 w-full bg-transparent text-sm focus:outline-none resize-none leading-relaxed text-foreground placeholder:text-muted-foreground/50 disabled:opacity-50"
                            value={selectedObjection.rebuttal || ''}
                            onChange={(e) => {
                              setSelectedObjection({...selectedObjection, rebuttal: e.target.value});
                              setIsDirtyObjection(true);
                            }}
                            placeholder="Instructions for the AI on how to handle this objection..."
                          />
                          
                          <div className="flex items-center justify-between mt-4 pt-4 border-t border-border/60">
                            <p className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
                              Tip: Be specific. Instead of "acknowledge and pivot", write the exact words the AI should use.
                            </p>
                            <div className={`text-xs font-medium ${(selectedObjection.rebuttal?.length || 0) > 4800 ? 'text-red-500' : 'text-muted-foreground'}`}>
                              {selectedObjection.rebuttal?.length || 0}/5000
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="p-5 border-t border-border/60 flex justify-between items-center bg-muted/10 mt-auto">
                        <button 
                          type="button"
                          onClick={() => handleDeleteObjection(selectedObjection.id)}
                          className="flex items-center gap-2 text-sm font-medium text-destructive hover:bg-destructive/10 px-3 py-2 rounded-lg transition-colors"
                        >
                          <Trash2 size={16} /> Delete
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
                          className={`px-5 py-2 text-sm font-semibold rounded-lg transition-all flex items-center justify-center min-w-[120px] shadow-xs cursor-pointer ${
                            isDirtyObjection || isSavingObjection
                              ? 'bg-primary hover:bg-primary/90 text-primary-foreground' 
                              : 'bg-muted text-muted-foreground cursor-not-allowed'
                          } disabled:opacity-50 ${isDirtyObjection && !isSavingObjection ? 'animate-pulse' : ''}`}
                        >
                          {isSavingObjection ? <div className="w-4 h-4 rounded-full border-2 border-primary-foreground border-t-transparent animate-spin" /> : 'Save Strategy'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full p-12 text-center relative overflow-hidden flex-1">
                      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none" />
                      
                      <div className="relative mb-6">
                        <div className="w-14 h-14 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-xs text-primary">
                          <ShieldAlert className="w-7 h-7 text-primary" />
                        </div>
                      </div>
                      
                      <h3 className="text-xl font-bold text-foreground mb-2 relative z-10">Select a Battle Playbook</h3>
                      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed mb-6 relative z-10">
                        Each playbook trains the AI to handle a specific objection your prospects raise — turning "not interested" into booked meetings.
                      </p>
                      
                      <div className="grid grid-cols-3 gap-3 w-full max-w-sm mb-8 relative z-10">
                        {['Too expensive', 'Wrong timing', 'Using competitor'].map((ex) => (
                          <div key={ex} className="bg-muted/40 rounded-lg p-3 text-center border border-border/60">
                            <p className="text-xs font-medium text-muted-foreground">{ex}</p>
                          </div>
                        ))}
                      </div>
                      
                      {(Array.isArray(objections) ? objections : []).length === 0 && (
                        <button
                          type="button"
                          onClick={handleAddObjection}
                          disabled={isCreatingObjection}
                          className="px-5 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-sm font-semibold transition-all shadow-xs flex items-center gap-2 disabled:opacity-50 relative z-10 cursor-pointer"
                        >
                          {isCreatingObjection ? <div className="w-4 h-4 rounded-full border-2 border-primary-foreground border-t-transparent animate-spin" /> : <Plus size={16} />}
                          Create Your First Playbook
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

      {/* DYNAMIC DOCUMENTATION MODAL (Prose format) */}
      <AnimatePresence>
        {isDocOpen && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-background/80 backdrop-blur-sm cursor-pointer"
              onClick={() => setIsDocOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-2xl bg-card border border-border/60 rounded-xl shadow-2xl overflow-hidden flex flex-col"
            >
              <div className={`absolute top-0 right-0 w-64 h-64 -mr-16 -mt-16 rounded-full bg-gradient-to-br ${activeDocData.color} opacity-10 blur-3xl pointer-events-none`} />
              
              <div className="relative p-6 pb-5 border-b border-border/60">
                <button 
                  type="button"
                  aria-label="Close documentation"
                  onClick={() => setIsDocOpen(false)}
                  className="absolute top-6 right-6 p-2 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                >
                  <X size={18} />
                </button>
                
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-muted/40 border border-border/60 rounded-lg flex items-center justify-center text-foreground shadow-xs">
                    {activeDocData.icon}
                  </div>
                  <div>
                    <h2 className="text-xl font-semibold tracking-tight text-foreground">{activeDocData.title}</h2>
                    <p className="text-muted-foreground text-[10px] font-bold uppercase tracking-widest mt-0.5">Documentation</p>
                  </div>
                </div>
              </div>

              <div className="relative p-6 pt-5 space-y-4 flex-1 overflow-y-auto">
                <div className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground leading-relaxed">
                  <p>{activeDocData.content}</p>
                </div>
              </div>

              <div className="p-4 bg-muted/20 border-t border-border/60 flex justify-end">
                <button 
                  type="button"
                  onClick={() => setIsDocOpen(false)}
                  className="px-5 py-2 bg-foreground text-background rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-all shadow-xs"
                >
                  Close
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isPasteModalOpen && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="absolute inset-0 bg-background/80 backdrop-blur-sm"
              onClick={() => setIsPasteModalOpen(false)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-card border border-border/60 shadow-2xl rounded-xl w-full max-w-lg p-6 overflow-hidden flex flex-col"
            >
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-foreground">Paste Knowledge</h3>
                <button 
                  type="button"
                  aria-label="Close"
                  onClick={() => setIsPasteModalOpen(false)} 
                  className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
              <input 
                type="text" 
                value={pasteTitle} 
                onChange={e => setPasteTitle(e.target.value)} 
                placeholder="Title (e.g. Competitor Battlecard)" 
                className="w-full bg-background border border-border/60 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary mb-4 text-foreground" 
              />
              <textarea 
                value={pasteText} 
                onChange={e => setPasteText(e.target.value)} 
                placeholder="Paste your raw text, emails, or notes here..." 
                className="w-full bg-background border border-border/60 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary min-h-[200px] mb-6 resize-none text-foreground" 
              />
              <div className="flex gap-3 w-full">
                <button 
                  type="button"
                  onClick={() => setIsPasteModalOpen(false)} 
                  className="flex-1 px-4 py-2.5 rounded-lg border border-border/60 text-foreground text-sm font-medium hover:bg-muted/50 transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={handlePasteText} 
                  disabled={isSavingPaste}
                  className="flex-1 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors shadow-xs disabled:opacity-50 flex items-center justify-center cursor-pointer"
                >
                  {isSavingPaste ? (
                    <div className="w-4 h-4 rounded-full border-2 border-primary-foreground border-t-transparent animate-spin" />
                  ) : (
                    'Save Text'
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {deletingAssetId && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="absolute inset-0 bg-background/80 backdrop-blur-sm"
              onClick={() => !isDeleting && setDeletingAssetId(null)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-card border border-border/60 shadow-2xl rounded-xl w-full max-w-sm p-6 overflow-hidden"
            >
              <div className="flex flex-col items-center text-center">
                <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
                  <Trash2 className="w-6 h-6 text-destructive" />
                </div>
                <h3 className="text-lg font-semibold text-foreground mb-2">Delete Asset?</h3>
                <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
                  Are you sure you want to permanently delete this asset? The AI will instantly lose all context derived from it.
                </p>
                <div className="flex gap-3 w-full">
                  <button 
                    type="button"
                    onClick={() => setDeletingAssetId(null)}
                    disabled={isDeleting}
                    className="flex-1 px-4 py-2.5 rounded-lg border border-border/60 text-foreground text-sm font-medium hover:bg-muted/50 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button 
                    type="button"
                    onClick={confirmDeleteAsset}
                    disabled={isDeleting}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 transition-colors shadow-xs disabled:opacity-50"
                  >
                    {isDeleting ? "Deleting..." : "Delete"}
                  </button>
                </div>
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