import { motion, AnimatePresence } from "motion/react";
import { Users, Plus, Edit2, Trash2, ShieldAlert, Sparkles, MessageSquare, X } from "lucide-react";
import { usePersonaForm } from "./hooks/usePersonaForm";

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

  return (
    <>
      <div className="bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[40px] p-8 lg:p-12 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 -mr-24 -mt-24 rounded-full bg-purple-100 dark:bg-purple-500/10 blur-[80px] pointer-events-none" />
        
        <div className="relative z-10">
          <div className="flex justify-between items-center mb-10">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-purple-500/20">
                <Users className="w-6 h-6 text-white" />
              </div>
              <div>
                <h3 className="text-2xl font-semibold tracking-tight text-foreground">Buyer Personas</h3>
                <p className="text-sm text-muted-foreground mt-1">Define who you are targeting to generate hyper-personalized hooks.</p>
              </div>
            </div>
            <button onClick={() => openPersonaModal()} className="flex items-center gap-2 bg-foreground text-background px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-foreground/90 transition-all hover:scale-105 active:scale-95 shadow-md">
              <Plus size={16} /> Add Persona
            </button>
          </div>
          
          {!personas || personas.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-3xl bg-slate-50/50 dark:bg-card/30">
              <div className="w-16 h-16 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center mb-4">
                <Users className="w-8 h-8 text-slate-400" />
              </div>
              <h4 className="text-lg font-medium text-foreground mb-2">No Buyer Personas Defined</h4>
              <p className="text-sm text-muted-foreground max-w-sm mb-6">Stop sending generic pitches. Define exact job titles and their specific pain points to drastically increase your reply rates.</p>
              <button onClick={() => openPersonaModal()} className="flex items-center gap-2 bg-purple-600 text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-purple-700 transition-colors shadow-md">
                <Plus size={16} /> Create Your First Persona
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {personas.map((persona: any) => (
                <div key={persona.id} className="group relative border border-slate-200 dark:border-slate-800/80 rounded-[32px] bg-white/50 dark:bg-[#0f1115]/50 hover:bg-white dark:hover:bg-[#15181e] hover:border-purple-300 dark:hover:border-purple-500/50 transition-all duration-300 overflow-hidden shadow-sm hover:shadow-xl">
                  {/* Card Header Background */}
                  <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-purple-50/50 dark:from-purple-900/10 to-transparent pointer-events-none" />
                  
                  <div className="p-8 relative z-10">
                    <div className="flex justify-between items-start mb-6">
                      <div>
                        <h3 className="text-xl font-semibold text-foreground mb-2 flex items-center gap-2">
                          {persona.title || persona.name}
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {Array.isArray(persona.target_titles) && persona.target_titles.length > 0 ? (
                            persona.target_titles.map((t: string, i: number) => (
                              <span key={i} className="px-2.5 py-1 rounded-md bg-purple-100 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 text-xs font-medium border border-purple-200 dark:border-purple-500/20">
                                {t}
                              </span>
                            ))
                          ) : (
                            <span className="px-2.5 py-1 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 text-xs font-medium">No target titles defined</span>
                          )}
                        </div>
                      </div>
                      <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity translate-x-2 group-hover:translate-x-0">
                        <button onClick={() => openPersonaModal(persona)} className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-muted-foreground hover:text-foreground hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"><Edit2 size={14} /></button>
                        <button onClick={() => handleDeletePersona(persona.id, persona.title)} className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-muted-foreground hover:text-destructive hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"><Trash2 size={14} /></button>
                      </div>
                    </div>
                    
                    <div className="space-y-6">
                      <div>
                        <div className="flex items-center gap-2 mb-3">
                          <ShieldAlert className="w-4 h-4 text-primary" />
                          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Pain Points</p>
                        </div>
                        <div className="text-sm text-foreground/80 leading-relaxed flex flex-col gap-1.5 pl-6 border-l-2 border-orange-200 dark:border-primary/20">
                          {Array.isArray(persona.pain_points) && persona.pain_points.length > 0
                            ? persona.pain_points.map((pt: any, i: number) => <span key={i} className="flex items-start"><span className="mr-2 opacity-50">•</span>{pt}</span>)
                            : <span className="text-muted-foreground italic">None defined</span>}
                        </div>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-6 pt-4 border-t border-slate-100 dark:border-slate-800/50">
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <Sparkles className="w-3.5 h-3.5 text-green-500" />
                            <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Value Prop</p>
                          </div>
                          <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3">
                            {persona.value_prop || <span className="text-muted-foreground italic text-xs">Inherits company default</span>}
                          </p>
                        </div>
                        
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
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
          <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 md:pl-[240px] pointer-events-auto">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="fixed inset-0 bg-black/80 backdrop-blur-sm" 
              onClick={() => setIsPersonaModalOpen(false)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.98, y: 10 }} 
              animate={{ opacity: 1, scale: 1, y: 0 }} 
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ type: "spring", damping: 25, stiffness: 400 }}
              className="relative w-full max-w-[600px] bg-[#0c0c0e] border border-white/10 rounded-2xl shadow-[0_0_50px_rgba(0,0,0,0.7)] flex flex-col max-h-[85vh] overflow-hidden"
            >
              {/* Header - Fixed */}
              <div className="shrink-0 px-6 py-4 border-b border-white/5 flex justify-between items-center bg-[#0c0c0e] z-10">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center">
                    <Users className="w-4 h-4 text-zinc-300" />
                  </div>
                  <h3 className="text-base font-semibold text-zinc-100">
                    {editingPersonaId ? 'Edit Persona' : 'New Persona'}
                  </h3>
                </div>
                <button 
                  onClick={() => setIsPersonaModalOpen(false)} 
                  className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 text-zinc-500 hover:text-white transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Body - Scrollable */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-gradient-to-b from-[#0c0c0e] to-[#050505]">
                
                {/* Name & Titles */}
                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-1.5">Persona Name</label>
                    <input 
                      type="text" 
                      value={personaForm.title} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, title: e.target.value}))}
                      className="w-full bg-transparent border border-white/10 rounded-lg px-4 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 hover:border-white/20 focus:outline-none focus:border-indigo-500/50 transition-all"
                      placeholder="e.g. Enterprise Sales VP"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-1.5">
                      Target Job Titles <span className="text-zinc-600 font-normal ml-1">(Comma separated)</span>
                    </label>
                    <input 
                      type="text" 
                      value={personaForm.target_titles} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, target_titles: e.target.value}))}
                      className="w-full bg-transparent border border-white/10 rounded-lg px-4 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 hover:border-white/20 focus:outline-none focus:border-indigo-500/50 transition-all"
                      placeholder="e.g. VP Sales, CRO, Head of Sales"
                    />
                  </div>
                </div>

                <div className="w-full h-px bg-white/5" />

                {/* AI Directives */}
                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-1.5">
                      Pain Points <span className="text-zinc-600 font-normal ml-1">(One per line)</span>
                    </label>
                    <textarea 
                      value={personaForm.pain_points} 
                      onChange={(e) => setPersonaForm(prev => ({...prev, pain_points: e.target.value}))}
                      className="w-full bg-transparent border border-white/10 rounded-lg px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 hover:border-white/20 focus:outline-none focus:border-primary/50 transition-all h-28 resize-none"
                      placeholder="e.g. Reps burning 10 hours a week on manual research.
Cold email conversion is flatlining."
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-5">
                    <div>
                      <label className="block text-sm font-medium text-zinc-300 mb-1.5">
                        Value Prop Override <span className="text-zinc-600 font-normal ml-1">(Optional)</span>
                      </label>
                      <textarea 
                        value={personaForm.value_prop} 
                        onChange={(e) => setPersonaForm(prev => ({...prev, value_prop: e.target.value}))}
                        className="w-full bg-transparent border border-white/10 rounded-lg px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 hover:border-white/20 focus:outline-none focus:border-emerald-500/50 transition-all h-20 resize-none"
                        placeholder="Why does this specific persona care about your product?"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-zinc-300 mb-1.5">
                        Tone Tweaks <span className="text-zinc-600 font-normal ml-1">(Optional)</span>
                      </label>
                      <textarea 
                        value={personaForm.tone_tweaks} 
                        onChange={(e) => setPersonaForm(prev => ({...prev, tone_tweaks: e.target.value}))}
                        className="w-full bg-transparent border border-white/10 rounded-lg px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 hover:border-white/20 focus:outline-none focus:border-blue-500/50 transition-all h-20 resize-none"
                        placeholder="e.g. Extremely concise, direct, highly metric-driven."
                      />
                    </div>
                  </div>
                </div>

              </div>

              {/* Footer - Fixed */}
              <div className="shrink-0 px-6 py-4 border-t border-white/5 bg-[#050505] flex justify-end gap-3 z-10">
                <button 
                  onClick={() => setIsPersonaModalOpen(false)} 
                  className="px-4 py-2 rounded-lg text-sm font-medium text-zinc-400 hover:text-white hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button 
                  onClick={handleSavePersona} 
                  className="bg-white hover:bg-zinc-200 text-black px-5 py-2 rounded-lg text-sm font-semibold transition-all shadow-[0_0_15px_rgba(255,255,255,0.1)]"
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
