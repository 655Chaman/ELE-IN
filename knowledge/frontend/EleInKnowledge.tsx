// ORCHESTRATOR: This file coordinates state only. Do NOT add UI rendering here. Add new UI sections as separate components in components/knowledge/

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { 
  BrainCircuit, Users, ShieldAlert, 
  UploadCloud, Link as LinkIcon, FileText, 
  Search, Plus, Trash2, Edit2, Play, MessageSquare, Sparkles, X, Database, RefreshCw
} from "lucide-react";


import { AddUrlModal } from "@/components/knowledge/AddUrlModal";
import { UploadPdfModal } from "@/components/knowledge/UploadPdfModal";
import { KnowledgeAssetList } from "@/components/knowledge/KnowledgeAssetList";
import { TestDriveSimulator } from "@/components/knowledge/TestDriveSimulator";
import { SynthesisEditor } from "@/components/knowledge/SynthesisEditor";
import { PersonaManager } from "@/components/knowledge/PersonaManager";
import { ReusableConfirmDialog } from "@/components/ReusableConfirmDialog";
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




  useEffect(() => {
    if (!workspace?.id) return;

    const channel = supabase.channel('knowledge-assets-changes')
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'knowledge_assets',
          filter: `workspace_id=eq.${workspace.id}`,
        },
        (payload) => {
          if (payload.new.status === 'synced' || payload.new.status === 'failed') {
            mutateAssets();
            if (payload.new.status === 'synced') {
              mutateSynthesis();
            }
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
  const [isScraping, setIsScraping] = useState(false);
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
    if (!pasteText.trim()) return toast.error("Please enter some text");
    if (!pasteTitle.trim()) return toast.error("Please enter a title");
    
    try {
      setIsScraping(true);
      setIsPasteModalOpen(false);
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
      mutateAssets();
      mutateSynthesis();
    } catch (e: any) {
      toast.error(e.message || "Failed to upload text");
    } finally {
      setIsScraping(false);
    }
  };

  
  const tabs = [
    { id: 'assets', label: "Company Info", icon: <Database size={14} /> },
    { id: 'personas', label: "Who You're Selling To", icon: <Users size={14} /> },
    { id: 'objections', label: "How to Handle Pushback", icon: <ShieldAlert size={14} /> },
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
      color: "from-purple-500 to-pink-500"
    },
    objections: {
      name: "Objection Playbook",
      icon: <ShieldAlert className="w-6 h-6" />,
      content: "AI is naturally agreeable and polite. If a prospect replies 'We use a competitor' or 'We don't have budget', a default AI might simply apologize and end the conversation. Your Objection Playbook explicitly trains the AI on your battle-tested counters. It learns to politely challenge the prospect and pivot the conversation—turning hesitant replies into booked meetings by handling friction exactly like your best senior Account Executive would.",
      color: "from-orange-500 to-red-500"
    }
  };

  const activeDocData = docsContext[activeTab];

  return (
    <div className="min-h-[100dvh] bg-background text-foreground font-sans overflow-x-hidden">
      <main className="max-w-[1200px] mx-auto p-6 md:p-8 lg:p-10">

      {/* ─── BLOCKING OVERLAY FOR SCRAPING ─────────────────────────────────────── */}
      <AnimatePresence>
        {isScraping && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[999] bg-background/60 backdrop-blur-md flex flex-col items-center justify-center p-4"
            style={{ pointerEvents: 'auto' }}
            onClick={(e) => {
              e.stopPropagation();
              toast.warning("The AI is currently digesting this website. Please do not navigate away so the knowledge graph isn't interrupted.");
            }}
          >
            <motion.div 
              initial={{ scale: 0.9, y: 10 }}
              animate={{ scale: 1, y: 0 }}
              className="bg-card border border-border/50 shadow-2xl rounded-3xl p-10 flex flex-col items-center text-center max-w-md w-full"
            >
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center border border-primary/20 mb-6 relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/20 to-purple-500/20 animate-spin" style={{ animationDuration: '3s' }} />
                <BrainCircuit className="w-8 h-8 text-primary relative z-10 animate-pulse" />
              </div>
              <h2 className="text-xl font-bold tracking-tight text-foreground mb-3">
                <ShinyText text="Digesting Knowledge..." speed={2} className="text-foreground" />
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Please wait a few moments while the AI scrapes, chunks, and embeds this website into your vector database. 
                <br/><br/>
                <span className="font-semibold text-foreground">Do not close or navigate away from this page.</span>
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

        
        {/* ─── HEADER ─────────────────────────────────────────────── */}
        <div className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            {/* Editable company name title */}
            {isEditingName ? (
              <div className="flex items-center gap-2 mb-2">
                <input
                  autoFocus
                  disabled={isSavingCompanyName}
                  value={editedCompanyName}
                  onChange={(e) => setEditedCompanyName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSaveCompanyName(); if (e.key === 'Escape') setIsEditingName(false); }}
                  className="text-2xl font-bold bg-transparent border-b-2 border-blue-500 focus:outline-none text-foreground pb-0.5 w-auto min-w-[200px] disabled:opacity-50"
                />
                <button 
                  onClick={handleSaveCompanyName} 
                  disabled={isSavingCompanyName}
                  className="text-xs px-3 py-1 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center min-w-[50px]"
                >
                  {isSavingCompanyName ? <div className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" /> : 'Save'}
                </button>
                <button 
                  onClick={() => setIsEditingName(false)} 
                  disabled={isSavingCompanyName}
                  className="text-xs px-3 py-1 bg-muted text-muted-foreground rounded-lg hover:bg-muted/80 disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <h1
                onClick={() => setIsEditingName(true)}
                title="Click to rename"
                className="text-2xl font-bold tracking-tight text-foreground mb-2 flex w-fit items-center gap-3 cursor-pointer group"
              >
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
                  <BrainCircuit className="w-4 h-4 text-primary" />
                </div>
                <span className="group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                  {workspace?.name ? `${workspace.name}'s Knowledge Base` : 'Your Knowledge Base'}
                </span>
                <Edit2 size={14} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </h1>
            )}
            <p className="text-sm text-muted-foreground max-w-lg">
              This is where your AI learns about your company. The more you add here, the smarter and more accurate your outreach becomes — no generic emails, ever.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsDocOpen(true)}
              className="flex items-center gap-2 px-4 py-2.5 bg-muted/30 border border-border/50 rounded-[18px] text-sm font-medium hover:bg-muted/50 transition-colors"
            >
              <FileText size={14} /> How it works
            </button>
            <TestDriveSimulator />
          </div>
        </div>

        {/* ─── PILL NAVIGATION (Matches Dashboard) ─────────────────────────────────── */}
        <div className="bg-muted/40 p-1 rounded-xl border border-border/50 w-full grid grid-cols-3 mb-8">
          {tabs.map((tab) => (
            <button 
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${activeTab === tab.id ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >
              {activeTab === tab.id && (
                <motion.div layoutId="kb-active-pill" className="absolute inset-0 bg-background shadow-sm border border-border/50 rounded-lg" transition={{ type: "spring", bounce: 0.2, duration: 0.6 }} />
              )}
              <span className="relative z-10 flex items-center justify-center gap-2">
                {tab.icon} {tab.label}
              </span>
            </button>
          ))}
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
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                
                {/* Data Sources (Spans 2 columns) */}
                <div className="md:col-span-2 group outline-none">
                  <div className="h-full bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[40px] p-8 lg:p-12 overflow-hidden relative shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-2xl">
                    <div className="absolute top-0 right-0 w-96 h-96 -mr-24 -mt-24 rounded-full bg-blue-100 dark:bg-blue-500/10 blur-[80px] pointer-events-none" />
                    
                    <div className="relative z-10">
                      {/* Section heading */}
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-500/20 border border-blue-100 dark:border-blue-500/30 flex items-center justify-center shadow-sm">
                          <Database className="w-5 h-5 text-blue-600 dark:text-blue-500" />
                        </div>
                        <div>
                          <h3 className="text-xl font-semibold tracking-tight text-foreground">Tell the AI about your company</h3>
                          <p className="text-xs text-muted-foreground mt-0.5">Add anything — your website, a sales deck, your pitch, notes. The AI reads it all.</p>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8 mt-6">

                        {/* ── 1. Upload PDF ── */}
                        <UploadPdfModal mutateAssets={mutateAssets} />

                        {/* ── 2. Scrape Website ── */}
                        <AddUrlModal />

                        {/* ── 3. Paste Text ── */}
                        <div
                          onClick={() => setIsPasteModalOpen(true)}
                          className="border border-slate-200 dark:border-border/50 bg-slate-50 dark:bg-muted/10 hover:bg-slate-100 dark:hover:bg-muted/20 transition-all rounded-3xl p-6 flex flex-col justify-between cursor-pointer"
                        >
                          <div>
                            <FileText size={20} className="text-foreground mb-2" />
                            <h3 className="font-semibold text-sm text-foreground">Copy-paste anything</h3>
                            <p className="text-xs text-muted-foreground mt-1 mb-3">Paste raw text, email templates, or notes directly.</p>
                          </div>
                          <button className="bg-foreground text-background py-2 rounded-xl text-xs font-semibold hover:bg-foreground/90 transition-colors w-full">
                            Open Editor
                          </button>
                        </div>
                      </div>

                      <div className="pt-6 border-t border-slate-100 dark:border-border/50">
                        <h4 className="text-sm font-semibold mb-1 text-foreground">What the AI has learned so far</h4>
                        <p className="text-xs text-muted-foreground mb-4">Each item below is part of your AI's memory. Delete any that are outdated.</p>
                        {(!assets && !assetsError) ? (
                          <div className="space-y-3">
                            {[1,2,3].map(i => <div key={i} className="h-16 w-full bg-slate-100 dark:bg-muted/50 rounded-2xl animate-pulse" />)}
                          </div>
                        ) : (!assets || (Array.isArray(assets) && assets.length === 0)) ? (
                          <div className="py-12 flex flex-col items-center justify-center text-center border-2 border-dashed border-slate-200 dark:border-border/50 rounded-3xl bg-slate-50/50 dark:bg-muted/5 mt-4">
                            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-muted flex items-center justify-center mb-4">
                              <BrainCircuit className="text-muted-foreground/40 w-6 h-6" />
                            </div>
                            <p className="text-sm font-semibold text-foreground">No knowledge items yet</p>
                            <p className="text-xs text-muted-foreground mt-1 max-w-xs">Add your website, a PDF, or paste some text above — the AI will learn from it instantly.</p>
                          </div>
                        ) : (
                          <KnowledgeAssetList assets={Array.isArray(assets) ? assets : []} onDelete={handleDeleteAsset} onRetry={handleRetryAsset} />
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
                  {[1,2,3].map(i => <div key={i} className="h-48 w-full bg-slate-100 dark:bg-muted/50 rounded-[40px] animate-pulse" />)}
                </div>
              ) : (
                <PersonaManager personas={personas} mutatePersonas={mutatePersonas} mutateObjections={mutateObjections} />
              )
            )}

{activeTab === 'objections' && (
              <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 min-h-[680px]">
                {/* LEFT SIDEBAR: "Battle Playbooks" */}
                <div className="bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[32px] flex flex-col shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-2xl overflow-hidden relative">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-red-500 to-orange-500 rounded-t-[32px]" />
                  <div className="relative z-10 flex flex-col h-full">
                    <div className="p-6 border-b border-slate-100 dark:border-border/40 flex justify-between items-start">
                      <div className="flex flex-col">
                        <span className="inline-block px-2 py-0.5 rounded-full bg-gradient-to-r from-red-500/10 to-orange-500/10 text-red-600 dark:text-red-400 text-[10px] font-bold uppercase tracking-wider mb-2 w-fit">Objection Engine</span>
                        <h3 className="text-lg font-bold text-foreground">Battle Playbooks</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {Array.isArray(objections) ? objections.length : 0} playbook{(Array.isArray(objections) ? objections.length : 0) === 1 ? '' : 's'} trained
                        </p>
                      </div>
                      <button 
                        onClick={handleAddObjection} 
                        disabled={isCreatingObjection} 
                        className="bg-red-500 hover:bg-red-600 text-white rounded-xl px-3 py-1.5 text-xs font-semibold flex items-center gap-1.5 disabled:opacity-50 transition-colors"
                      >
                        {isCreatingObjection ? <div className="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" /> : <Plus size={14} />}
                        <span className="hidden sm:inline">New Playbook</span>
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-2">
                      {isObjectionsLoading ? (
                        [1,2,3,4].map(i => <div key={i} className="h-16 w-full bg-slate-100 dark:bg-muted/50 rounded-2xl animate-pulse" />)
                      ) : (
                        (Array.isArray(objections) ? objections : []).length === 0 ? (
                          <div className="flex flex-col items-center justify-center flex-1 py-12 text-center h-full">
                            <div className="w-12 h-12 rounded-2xl bg-red-50 dark:bg-red-950/30 border border-red-100 dark:border-red-800/40 flex items-center justify-center mb-3">
                              <ShieldAlert className="w-6 h-6 text-red-400" />
                            </div>
                            <p className="text-sm font-medium text-foreground mb-1">No playbooks yet</p>
                            <p className="text-xs text-muted-foreground mb-4 px-4">Create your first objection handler to train the AI on how to respond to pushback.</p>
                            <button onClick={handleAddObjection} disabled={isCreatingObjection} className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-xl text-xs font-semibold transition-colors flex items-center justify-center min-w-[140px]">
                              {isCreatingObjection ? <div className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> : 'Create First Playbook'}
                            </button>
                          </div>
                        ) : (
                          (Array.isArray(objections) ? objections : []).map((obj: any) => (
                            <div
                              key={obj.id}
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
                              className={`group p-4 rounded-2xl cursor-pointer transition-all border ${
                                selectedObjection?.id === obj.id
                                  ? 'bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-950/40 dark:to-orange-950/40 border-red-200 dark:border-red-800/50 shadow-sm'
                                  : 'border-transparent hover:bg-slate-50 dark:hover:bg-muted/30 hover:border-slate-200 dark:hover:border-border/50'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-semibold text-foreground truncate">{obj.name || 'Untitled Objection'}</p>
                                  <p className="text-xs text-muted-foreground mt-0.5 truncate">{obj.rebuttal?.substring(0, 60) || 'No strategy yet'}...</p>
                                </div>
                                <button
                                  onClick={(e) => { e.stopPropagation(); handleDeleteObjection(obj.id); }}
                                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-950/50 text-red-400 hover:text-red-600 shrink-0 mt-0.5"
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
                <div className="bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[32px] shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-2xl overflow-hidden flex flex-col relative">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-red-500 to-orange-500 rounded-t-[32px]" />
                  {selectedObjection ? (
                    <div className="flex-1 flex flex-col relative z-10">
                      {/* Status bar */}
                      <div className="px-6 py-3 border-b border-slate-100 dark:border-border/40 flex items-center gap-3 bg-slate-50/50 dark:bg-muted/5">
                        <div className="flex items-center gap-1.5">
                          <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                          <span className="text-[10px] font-bold text-red-500 uppercase tracking-wider">Editing Playbook</span>
                        </div>
                        <span className="text-slate-300 dark:text-border">/</span>
                        <span className="text-xs font-medium text-muted-foreground truncate">{selectedObjection.name || 'Untitled'}</span>
                      </div>

                      <div className="p-6 md:p-8 flex flex-col gap-6 flex-1 overflow-y-auto">
                        {/* Trigger Phrase Card */}
                        <div className="bg-gradient-to-r from-red-500/5 to-orange-500/5 border border-red-200/50 dark:border-red-800/40 rounded-3xl p-6 shadow-sm">
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
                        <div className="flex-1 bg-white dark:bg-background/50 border border-slate-200 dark:border-border/50 rounded-3xl p-6 flex flex-col shadow-sm">
                          <div className="flex justify-between items-center mb-3">
                            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">AI Response Strategy</label>
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
                          
                          <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-100 dark:border-border/50">
                            <p className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
                              💡 Tip: Be specific. Instead of "acknowledge and pivot", write the exact words the AI should use.
                            </p>
                            <div className={`text-xs font-medium ${(selectedObjection.rebuttal?.length || 0) > 4800 ? 'text-red-500' : 'text-muted-foreground'}`}>
                              {selectedObjection.rebuttal?.length || 0}/5000
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="p-6 border-t border-slate-100 dark:border-border/40 flex justify-between items-center bg-slate-50/50 dark:bg-muted/5 mt-auto">
                        <button 
                          onClick={() => handleDeleteObjection(selectedObjection.id)}
                          className="flex items-center gap-2 text-sm font-medium text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 px-3 py-2 rounded-xl transition-colors"
                        >
                          <Trash2 size={16} /> Delete
                        </button>

                        <button 
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
                          className={`px-6 py-2.5 text-sm font-bold rounded-xl transition-all flex items-center justify-center min-w-[120px] shadow-sm ${
                            isDirtyObjection || isSavingObjection
                              ? 'bg-gradient-to-r from-red-500 to-orange-500 text-white shadow-lg shadow-red-500/20 hover:opacity-90' 
                              : 'bg-slate-100 dark:bg-muted text-muted-foreground cursor-not-allowed'
                          } disabled:opacity-50 ${isDirtyObjection && !isSavingObjection ? 'animate-pulse' : ''}`}
                        >
                          {isSavingObjection ? <div className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> : 'Save Strategy'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full p-12 text-center relative overflow-hidden flex-1">
                      <div className="absolute inset-0 bg-gradient-to-br from-red-500/3 via-orange-500/3 to-transparent pointer-events-none" />
                      <div className="absolute -bottom-20 -right-20 w-64 h-64 rounded-full bg-orange-100 dark:bg-orange-500/10 blur-[80px] pointer-events-none" />
                      
                      <div className="relative mb-6">
                        <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center shadow-lg shadow-red-500/20">
                          <ShieldAlert className="w-10 h-10 text-white" />
                        </div>
                        <div className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-amber-400 border-2 border-background flex items-center justify-center">
                          <Sparkles className="w-3 h-3 text-white" />
                        </div>
                      </div>
                      
                      <h3 className="text-xl font-bold text-foreground mb-2 relative z-10">Select a Battle Playbook</h3>
                      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed mb-6 relative z-10">
                        Each playbook trains the AI to handle a specific objection your prospects raise — turning "not interested" into booked meetings.
                      </p>
                      
                      <div className="grid grid-cols-3 gap-3 w-full max-w-sm mb-8 relative z-10">
                        {['Too expensive', 'Wrong timing', 'Using competitor'].map((ex) => (
                          <div key={ex} className="bg-slate-100 dark:bg-muted/40 rounded-xl p-3 text-center border border-slate-200 dark:border-border/50">
                            <p className="text-xs font-medium text-muted-foreground">{ex}</p>
                          </div>
                        ))}
                      </div>
                      
                      {(Array.isArray(objections) ? objections : []).length === 0 && (
                        <button
                          onClick={handleAddObjection}
                          disabled={isCreatingObjection}
                          className="px-6 py-3 bg-gradient-to-r from-red-500 to-orange-500 text-white rounded-2xl text-sm font-bold hover:opacity-90 transition-opacity shadow-lg shadow-red-500/20 flex items-center gap-2 disabled:opacity-50 relative z-10"
                        >
                          {isCreatingObjection ? <div className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> : <Plus size={16} />}
                          Create Your First Playbook
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
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
              className="relative w-full max-w-2xl bg-white dark:bg-card border border-slate-200 dark:border-border/50 rounded-[40px] shadow-[0_8px_40px_rgb(0,0,0,0.12)] dark:shadow-2xl overflow-hidden flex flex-col"
            >
              <div className={`absolute top-0 right-0 w-64 h-64 -mr-16 -mt-16 rounded-full bg-gradient-to-br ${activeDocData.color} opacity-10 blur-3xl pointer-events-none`} />
              
              <div className="relative p-10 pb-6 border-b border-slate-100 dark:border-border/40">
                <button 
                  onClick={() => setIsDocOpen(false)}
                  className="absolute top-8 right-8 p-2 rounded-full hover:bg-slate-100 dark:hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors"
                >
                  <X size={20} />
                </button>
                
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-slate-50 dark:bg-muted/30 border border-slate-200 dark:border-border/50 rounded-2xl flex items-center justify-center text-foreground shadow-sm">
                    {activeDocData.icon}
                  </div>
                  <div>
                    <h2 className="text-2xl font-light tracking-tight text-foreground">{activeDocData.title}</h2>
                    <p className="text-muted-foreground text-xs font-bold uppercase tracking-widest mt-1">Documentation</p>
                  </div>
                </div>
              </div>

              <div className="relative p-10 pt-6 space-y-6 flex-1 overflow-y-auto">
                <div className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground leading-relaxed">
                  <p>{activeDocData.content}</p>
                </div>
              </div>

              <div className="p-8 bg-slate-50 dark:bg-muted/20 border-t border-slate-100 dark:border-border/40 flex justify-end">
                <button 
                  onClick={() => setIsDocOpen(false)}
                  className="px-6 py-2.5 bg-foreground text-background rounded-xl text-sm font-semibold hover:bg-foreground/90 transition-all shadow-sm"
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
              className="absolute inset-0 bg-slate-900/20 dark:bg-black/40 backdrop-blur-sm"
              onClick={() => setIsPasteModalOpen(false)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-white dark:bg-card border border-slate-200 dark:border-border/50 shadow-2xl rounded-3xl w-full max-w-lg p-6 overflow-hidden flex flex-col"
            >
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-foreground">Paste Knowledge</h3>
                <button onClick={() => setIsPasteModalOpen(false)} className="text-muted-foreground hover:text-foreground"><X size={18} /></button>
              </div>
              <input type="text" value={pasteTitle} onChange={e => setPasteTitle(e.target.value)} placeholder="Title (e.g. Competitor Battlecard)" className="w-full bg-slate-50 dark:bg-muted/10 border border-slate-200 dark:border-border/50 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 mb-4" />
              <textarea value={pasteText} onChange={e => setPasteText(e.target.value)} placeholder="Paste your raw text, emails, or notes here..." className="w-full bg-slate-50 dark:bg-muted/10 border border-slate-200 dark:border-border/50 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[200px] mb-6 resize-none" />
              <div className="flex gap-3 w-full">
                <button onClick={() => setIsPasteModalOpen(false)} className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-border/50 text-foreground text-sm font-medium hover:bg-slate-50 dark:hover:bg-muted/50 transition-colors">Cancel</button>
                <button onClick={handlePasteText} className="flex-1 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">Save Text</button>
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
              className="absolute inset-0 bg-slate-900/20 dark:bg-black/40 backdrop-blur-sm"
              onClick={() => !isDeleting && setDeletingAssetId(null)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-white dark:bg-card border border-slate-200 dark:border-border/50 shadow-2xl rounded-3xl w-full max-w-sm p-6 overflow-hidden"
            >
              <div className="flex flex-col items-center text-center">
                <div className="w-12 h-12 rounded-full bg-red-50 dark:bg-red-500/10 flex items-center justify-center mb-4">
                  <Trash2 className="w-6 h-6 text-red-500" />
                </div>
                <h3 className="text-lg font-semibold text-foreground mb-2">Delete Asset?</h3>
                <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
                  Are you sure you want to permanently delete this asset? The AI will instantly lose all context derived from it.
                </p>
                <div className="flex gap-3 w-full">
                  <button 
                    onClick={() => setDeletingAssetId(null)}
                    disabled={isDeleting}
                    className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-border/50 text-foreground text-sm font-medium hover:bg-slate-50 dark:hover:bg-muted/50 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button 
                    onClick={confirmDeleteAsset}
                    disabled={isDeleting}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition-colors shadow-sm shadow-red-500/20 disabled:opacity-50"
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