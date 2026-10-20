import { motion, AnimatePresence } from "motion/react";
import { Users, Plus, Edit2, Trash2, ShieldAlert, Sparkles, MessageSquare, X, Lock } from "lucide-react";
import { usePersonaForm } from "./hooks/usePersonaForm";
import { usePaywall } from "@/contexts/PaywallContext";
import useSWR from "swr";
import { fetcher } from "@/lib/apiClient";
import { toast } from "sonner";

export function PersonaManager({ personas, mutatePersonas, mutateObjections }: { personas: any[], mutatePersonas: any, mutateObjections: any }) {
  const {
    isPersonaModalOpen, setIsPersonaModalOpen,
    editingPersonaId,
    personaForm, setPersonaForm,
    openPersonaModal,
    handleSavePersona,
    handleDeletePersona
  } = usePersonaForm(personas, mutatePersonas, mutateObjections);

  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const tier = billingData?.tier || 'FREE';
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE';
  const maxPersonas = isPro ? (tier === 'ENTERPRISE' ? 50 : 10) : 1;
  const isPersonaCapped = !isPro && (personas || []).length >= maxPersonas;

  const handleAddPersonaClick = () => {
    if (isPersonaCapped) {
      openPaywall({ featureName: "Multi-Persona Target Engine" });
      toast.info(`Free plan is limited to ${maxPersonas} buyer persona. Upgrade to Growth Pro to define up to 10 target personas.`);
      return;
    }
    openPersonaModal();
  };

  return (
    <>
      <div className="bg-card/40 border border-border/50 rounded-xl p-6 lg:p-7 relative overflow-hidden">
        <div className="relative z-10">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shadow-2xs">
                <Users className="w-4 h-4 text-foreground/80" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-medium tracking-tight text-foreground">Buyer Personas</h3>
                  {!isPro && (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50 font-mono">
                      {(personas || []).length}/{maxPersonas}
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Pitching a CTO like a CFO gets your emails marked as spam. Personas tell the AI who reads each message so credits aren't wasted on tone-deaf copy.
                </p>
              </div>
            </div>
            <button 
              type="button"
              onClick={handleAddPersonaClick} 
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                isPersonaCapped 
                  ? "border border-border/60 bg-muted/40 text-muted-foreground hover:bg-muted/60" 
                  : "bg-foreground text-background hover:bg-foreground/90 shadow-2xs"
              }`}
            >
              {isPersonaCapped ? <Lock size={12} className="text-amber-500" /> : <Plus size={13} />}
              {isPersonaCapped ? "Unlock More Personas" : "Add Persona"}
            </button>
          </div>
          
          {!personas || personas.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-4 text-center border border-dashed border-border/60 rounded-xl bg-card/20">
              <div className="w-10 h-10 bg-muted/60 border border-border/40 rounded-lg flex items-center justify-center mb-3 text-muted-foreground">
                <Users className="w-5 h-5 text-muted-foreground" />
              </div>
              <h4 className="text-sm font-medium text-foreground mb-1">No Buyer Personas Defined</h4>
              <p className="text-xs text-muted-foreground max-w-md mb-5 leading-relaxed">
                Pitching quota metrics to a CTO gets deleted in seconds. Define your buyer personas so the AI speaks their language, addresses their specific daily pain points, and maximizes reply rates per credit spent.
              </p>
              <button 
                type="button"
                onClick={() => openPersonaModal()} 
                className="flex items-center gap-1.5 bg-foreground text-background hover:bg-foreground/90 px-4 py-2 rounded-lg text-xs font-medium transition-colors shadow-2xs cursor-pointer"
              >
                <Plus size={13} /> Create First Persona
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {personas.map((persona: any) => (
                <div key={persona.id} className="group border border-border/50 rounded-xl bg-card/40 hover:bg-card/70 hover:border-border/80 transition-all p-5 shadow-2xs">
                  <div className="flex justify-between items-start gap-3 mb-4">
                    <div>
                      <h4 className="text-sm font-medium text-foreground mb-1.5 flex items-center gap-2">
                        {persona.title || persona.name}
                      </h4>
                      <div className="flex flex-wrap gap-1.5">
                        {Array.isArray(persona.target_titles) && persona.target_titles.length > 0 ? (
                          persona.target_titles.map((t: string, i: number) => (
                            <span key={i} className="px-2 py-0.5 rounded-md bg-muted/60 text-muted-foreground text-[11px] font-medium border border-border/40">
                              {t}
                            </span>
                          ))
                        ) : (
                          <span className="px-2 py-0.5 rounded-md bg-muted/40 text-muted-foreground text-[11px]">No target titles defined</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      <button 
                        type="button"
                        aria-label="Edit persona"
                        onClick={() => openPersonaModal(persona)} 
                        className="w-7 h-7 flex items-center justify-center rounded-md bg-muted/50 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                      >
                        <Edit2 size={12} />
                      </button>
                      <button 
                        type="button"
                        aria-label="Delete persona"
                        onClick={() => handleDeletePersona(persona.id, persona.title)} 
                        className="w-7 h-7 flex items-center justify-center rounded-md bg-muted/50 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  
                  <div className="space-y-4">
                    <div>
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <ShieldAlert className="w-3.5 h-3.5 text-muted-foreground" />
                        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Pain Points</span>
                      </div>
                      <div className="text-xs text-foreground/85 leading-relaxed flex flex-col gap-1 p-2.5 rounded-lg bg-muted/20 border border-border/40">
                        {Array.isArray(persona.pain_points) && persona.pain_points.length > 0
                          ? persona.pain_points.map((pt: any, i: number) => <span key={i} className="flex items-start"><span className="mr-1.5 opacity-40">•</span>{pt}</span>)
                          : <span className="text-muted-foreground italic">None defined</span>}
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 pt-3 border-t border-border/40">
                      <div>
                        <div className="flex items-center gap-1.5 mb-1">
                          <Sparkles className="w-3 h-3 text-muted-foreground" />
                          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Value Prop</span>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                          {persona.value_prop || <span className="italic">Inherits company default</span>}
                        </p>
                      </div>
                      
                      <div>
                        <div className="flex items-center gap-1.5 mb-1">
                          <MessageSquare className="w-3 h-3 text-muted-foreground" />
                          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Tone Tweaks</span>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                          {persona.tone_tweaks || <span className="italic">No special instructions</span>}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {/* Modal Injection */}
      <AnimatePresence>
        {isPersonaModalOpen && (
          <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 pointer-events-auto">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="fixed inset-0 bg-background/80 backdrop-blur-sm cursor-pointer" 
              onClick={() => setIsPersonaModalOpen(false)}
            />
            <motion.div 
              role="dialog"
              aria-modal="true"
              aria-labelledby="persona-modal-title"
              initial={{ opacity: 0, scale: 0.98, y: 10 }} 
              animate={{ opacity: 1, scale: 1, y: 0 }} 
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ type: "spring", damping: 25, stiffness: 400 }}
              className="relative w-full max-w-[560px] bg-card border border-border/60 rounded-xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden"
            >
              {/* Header - Fixed */}
              <div className="shrink-0 px-5 py-4 border-b border-border/50 flex justify-between items-center bg-card z-10">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80">
                    <Users className="w-3.5 h-3.5" />
                  </div>
                  <h3 id="persona-modal-title" className="text-sm font-medium text-foreground">
                    {editingPersonaId ? 'Edit Persona' : 'New Persona'}
                  </h3>
                </div>
                <button 
                  type="button"
                  onClick={() => setIsPersonaModalOpen(false)} 
                  aria-label="Close modal"
                  className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <X size={15} />
                </button>
              </div>

              {/* Body - Scrollable */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-card text-xs">
                
                {/* Name & Titles */}
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-foreground mb-1.5">Persona Name</label>
                    <input 
                      type="text" 
                      value={personaForm.title} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, title: e.target.value}))}
                      className="w-full bg-background border border-border/60 rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring transition-colors"
                      placeholder="e.g. Enterprise Sales VP"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs font-medium text-foreground mb-1.5">
                      Target Job Titles <span className="text-muted-foreground font-normal ml-1">(Comma separated)</span>
                    </label>
                    <input 
                      type="text" 
                      value={personaForm.target_titles} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, target_titles: e.target.value}))}
                      className="w-full bg-background border border-border/60 rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring transition-colors"
                      placeholder="e.g. VP Sales, CRO, Head of Sales"
                    />
                  </div>
                </div>

                <div className="w-full h-px bg-border/40 my-2" />

                {/* AI Directives */}
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-foreground mb-1.5">
                      Pain Points <span className="text-muted-foreground font-normal ml-1">(One per line)</span>
                    </label>
                    <textarea 
                      value={personaForm.pain_points} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, pain_points: e.target.value}))}
                      className="w-full bg-background border border-border/60 rounded-lg px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring transition-colors h-24 resize-none leading-relaxed"
                      placeholder="e.g. Reps burning 10 hours a week on manual research.&#10;Cold email conversion is flatlining."
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-foreground mb-1.5">
                        Value Prop Override <span className="text-muted-foreground font-normal ml-1">(Optional)</span>
                      </label>
                      <textarea 
                        value={personaForm.value_prop} 
                        onChange={(e) => setPersonaForm(prev => ({...prev, value_prop: e.target.value}))}
                        className="w-full bg-background border border-border/60 rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring transition-colors h-16 resize-none leading-relaxed"
                        placeholder="Why does this specific persona care about your product?"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-foreground mb-1.5">
                        Tone Tweaks <span className="text-muted-foreground font-normal ml-1">(Optional)</span>
                      </label>
                      <textarea 
                        value={personaForm.tone_tweaks} 
                        onChange={(e) => setPersonaForm(prev => ({...prev, tone_tweaks: e.target.value}))}
                        className="w-full bg-background border border-border/60 rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring transition-colors h-16 resize-none leading-relaxed"
                        placeholder="e.g. Extremely concise, direct, highly metric-driven."
                      />
                    </div>
                  </div>
                </div>

              </div>

              {/* Footer - Fixed */}
              <div className="shrink-0 px-5 py-3.5 border-t border-border/50 bg-muted/20 flex justify-end gap-2 z-10">
                <button 
                  type="button"
                  onClick={() => setIsPersonaModalOpen(false)} 
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={handleSavePersona} 
                  className="bg-foreground text-background hover:bg-foreground/90 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors shadow-2xs cursor-pointer"
                >
                  Save Persona
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
