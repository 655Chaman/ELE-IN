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
    handleAddPersona,
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
      <div className="bg-card border border-border/60 rounded-xl p-8 lg:p-12 shadow-sm relative overflow-hidden">
        <div className="relative z-10">
          <div className="flex justify-between items-center mb-10">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
                <Users className="w-6 h-6 text-primary" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-2xl font-semibold tracking-tight text-foreground">Buyer Personas</h3>
                  {!isPro && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                      {(personas || []).length}/{maxPersonas} Personas
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground mt-1">Define who you are targeting to generate hyper-personalized hooks.</p>
              </div>
            </div>
            <button 
              type="button"
              onClick={handleAddPersonaClick} 
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors shadow-sm ${
                isPersonaCapped 
                  ? "bg-muted text-foreground border border-border" 
                  : "bg-primary text-primary-foreground hover:bg-primary/90"
              }`}
            >
              {isPersonaCapped ? <Lock size={15} className="text-amber-500" /> : <Plus size={16} />}
              {isPersonaCapped ? "Unlock More Personas" : "Add Persona"}
            </button>
          </div>
          
          {!personas || personas.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center border-2 border-dashed border-border/60 rounded-lg bg-muted/20">
              <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mb-4">
                <Users className="w-8 h-8 text-muted-foreground" />
              </div>
              <h4 className="text-lg font-medium text-foreground mb-2">No Buyer Personas Defined</h4>
              <p className="text-sm text-muted-foreground max-w-sm mb-6">Stop sending generic pitches. Define exact job titles and their specific pain points to drastically increase your reply rates.</p>
              <button 
                type="button"
                onClick={() => openPersonaModal()} 
                className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-2.5 rounded-lg text-sm font-semibold hover:bg-primary/90 transition-colors shadow-sm"
              >
                <Plus size={16} /> Create Your First Persona
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {personas.map((persona: any) => (
                <div key={persona.id} className="group relative border border-border/60 rounded-lg bg-card hover:border-border transition-colors shadow-xs overflow-hidden">
                  <div className="p-8 relative z-10">
                    <div className="flex justify-between items-start mb-6">
                      <div>
                        <h3 className="text-xl font-semibold text-foreground mb-2 flex items-center gap-2">
                          {persona.title || persona.name}
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {Array.isArray(persona.target_titles) && persona.target_titles.length > 0 ? (
                            persona.target_titles.map((t: string, i: number) => (
                              <span key={i} className="px-2.5 py-1 rounded-md bg-primary/10 text-primary text-xs font-medium border border-primary/20">
                                {t}
                              </span>
                            ))
                          ) : (
                            <span className="px-2.5 py-1 rounded-md bg-muted text-muted-foreground text-xs font-medium">No target titles defined</span>
                          )}
                        </div>
                      </div>
                      <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button 
                          type="button"
                          aria-label="Edit persona"
                          onClick={() => openPersonaModal(persona)} 
                          className="w-8 h-8 flex items-center justify-center rounded-lg bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors"
                        >
                          <Edit2 size={14} />
                        </button>
                        <button 
                          type="button"
                          aria-label="Delete persona"
                          onClick={() => handleDeletePersona(persona.id, persona.title)} 
                          className="w-8 h-8 flex items-center justify-center rounded-lg bg-muted text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                    
                    <div className="space-y-6">
                      <div>
                        <div className="flex items-center gap-2 mb-3">
                          <ShieldAlert className="w-4 h-4 text-primary" />
                          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Pain Points</p>
                        </div>
                        <div className="text-sm text-foreground/80 leading-relaxed flex flex-col gap-1.5 p-3 rounded-lg bg-muted/30 border border-border/50">
                          {Array.isArray(persona.pain_points) && persona.pain_points.length > 0
                            ? persona.pain_points.map((pt: any, i: number) => <span key={i} className="flex items-start"><span className="mr-2 opacity-50">•</span>{pt}</span>)
                            : <span className="text-muted-foreground italic">None defined</span>}
                        </div>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-6 pt-4 border-t border-border/50">
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
                            <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Value Prop</p>
                          </div>
                          <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3">
                            {persona.value_prop || <span className="text-muted-foreground italic text-xs">Inherits company default</span>}
                          </p>
                        </div>
                        
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <MessageSquare className="w-3.5 h-3.5 text-primary" />
                            <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Tone Tweaks</p>
                          </div>
                          <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3">
                            {persona.tone_tweaks || <span className="text-muted-foreground italic text-xs">No special instructions</span>}
                          </p>
                        </div>
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
              className="fixed inset-0 bg-background/80 backdrop-blur-sm" 
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
              className="relative w-full max-w-[600px] bg-card border border-border rounded-xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden"
            >
              {/* Header - Fixed */}
              <div className="shrink-0 px-6 py-4 border-b border-border flex justify-between items-center bg-card z-10">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                    <Users className="w-4 h-4 text-primary" />
                  </div>
                  <h3 id="persona-modal-title" className="text-base font-semibold text-foreground">
                    {editingPersonaId ? 'Edit Persona' : 'New Persona'}
                  </h3>
                </div>
                <button 
                  type="button"
                  onClick={() => setIsPersonaModalOpen(false)} 
                  aria-label="Close modal"
                  className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Body - Scrollable */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-card">
                
                {/* Name & Titles */}
                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">Persona Name</label>
                    <input 
                      type="text" 
                      value={personaForm.title} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, title: e.target.value}))}
                      className="w-full bg-background border border-border rounded-lg px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground hover:border-border/80 focus:outline-none focus:border-primary transition-colors"
                      placeholder="e.g. Enterprise Sales VP"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Target Job Titles <span className="text-muted-foreground font-normal ml-1">(Comma separated)</span>
                    </label>
                    <input 
                      type="text" 
                      value={personaForm.target_titles} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, target_titles: e.target.value}))}
                      className="w-full bg-background border border-border rounded-lg px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground hover:border-border/80 focus:outline-none focus:border-primary transition-colors"
                      placeholder="e.g. VP Sales, CRO, Head of Sales"
                    />
                  </div>
                </div>

                <div className="w-full h-px bg-border" />

                {/* AI Directives */}
                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Pain Points <span className="text-muted-foreground font-normal ml-1">(One per line)</span>
                    </label>
                    <textarea 
                      value={personaForm.pain_points} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, pain_points: e.target.value}))}
                      className="w-full bg-background border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground hover:border-border/80 focus:outline-none focus:border-primary transition-colors h-28 resize-none"
                      placeholder="e.g. Reps burning 10 hours a week on manual research.
Cold email conversion is flatlining."
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-5">
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-1.5">
                        Value Prop Override <span className="text-muted-foreground font-normal ml-1">(Optional)</span>
                      </label>
                      <textarea 
                        value={personaForm.value_prop} 
                        onChange={(e) => setPersonaForm(prev => ({...prev, value_prop: e.target.value}))}
                        className="w-full bg-background border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground hover:border-border/80 focus:outline-none focus:border-primary transition-colors h-20 resize-none"
                        placeholder="Why does this specific persona care about your product?"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-1.5">
                        Tone Tweaks <span className="text-muted-foreground font-normal ml-1">(Optional)</span>
                      </label>
                      <textarea 
                        value={personaForm.tone_tweaks} 
                        onChange={(e) => setPersonaForm(prev => ({...prev, tone_tweaks: e.target.value}))}
                        className="w-full bg-background border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground hover:border-border/80 focus:outline-none focus:border-primary transition-colors h-20 resize-none"
                        placeholder="e.g. Extremely concise, direct, highly metric-driven."
                      />
                    </div>
                  </div>
                </div>

              </div>

              {/* Footer - Fixed */}
              <div className="shrink-0 px-6 py-4 border-t border-border bg-muted/30 flex justify-end gap-3 z-10">
                <button 
                  type="button"
                  onClick={() => setIsPersonaModalOpen(false)} 
                  className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={handleSavePersona} 
                  className="bg-primary hover:bg-primary/90 text-primary-foreground px-5 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm"
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
