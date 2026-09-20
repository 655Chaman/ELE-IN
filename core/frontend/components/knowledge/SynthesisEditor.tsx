import { Edit2, Sparkles } from "lucide-react";
import { useSynthesisForm } from "./hooks/useSynthesisForm";

export function SynthesisEditor({ synthesis, mutateSynthesis }: { synthesis: any, mutateSynthesis: () => void }) {
  const {
    isEditingSynthesis, setIsEditingSynthesis,
    editedValueProp, setEditedValueProp,
    editedTone, setEditedTone,
    editedTargetCustomer, setEditedTargetCustomer,
    editedDifferentiators, setEditedDifferentiators,
    editedProofPoints, setEditedProofPoints,
    editedPainPoints, setEditedPainPoints,
    editedBannedPhrases, setEditedBannedPhrases,
    editedObjectionPlaybook, setEditedObjectionPlaybook,
    handleSaveSynthesis,
    isSaving
  } = useSynthesisForm(synthesis, mutateSynthesis);

  return (
    <div className="md:col-span-1 group outline-none">
      <div className="h-full bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[40px] p-8 overflow-hidden relative shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-2xl">
        <div className="absolute top-0 right-0 w-64 h-64 -mr-16 -mt-16 rounded-full bg-orange-100 dark:bg-primary/10 blur-[60px] pointer-events-none" />
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-6">

            <div className="w-10 h-10 rounded-xl bg-orange-50 dark:bg-primary/20 border border-orange-100 dark:border-primary/30 flex items-center justify-center shadow-sm">
              <Sparkles className="w-5 h-5 text-orange-600 dark:text-primary" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">What the AI understood</h3>
              <p className="text-xs text-muted-foreground">Auto-generated from your content</p>
            </div>
          </div>

          <div className="space-y-6">
            <div>
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="font-semibold text-foreground">AI Readiness</span>
                <span className={`font-bold ${synthesis?.core_value_prop ? 'text-green-600 dark:text-green-500' : 'text-orange-600 dark:text-primary'}`}>
                  {synthesis?.core_value_prop ? '✓ Ready to write DMs' : 'Add content above'}
                </span>
              </div>
              <div className="h-2 w-full bg-slate-100 dark:bg-muted rounded-full overflow-hidden">
                <div className={`h-full transition-all duration-700 ${synthesis?.core_value_prop ? 'bg-green-500 w-full' : 'bg-primary w-[15%]'}`} />
              </div>
              <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
                {synthesis?.core_value_prop
                  ? "Your AI will now write DMs that specifically reference your product's benefits and your company's unique angle — not generic filler."
                  : "Without context, the AI writes generic emails. Add your website or a PDF above and it'll learn your voice, product, and value within seconds."}
              </p>
            </div>
            
            <div className="pt-6 border-t border-slate-100 dark:border-border/50">
               <div className="flex justify-between items-center mb-2">
                 <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block">Core Value Prop</span>
                 {synthesis?.core_value_prop && !isEditingSynthesis && (
                   <button onClick={() => setIsEditingSynthesis(true)} className="text-[10px] text-blue-500 hover:text-blue-600 font-semibold flex items-center gap-1"><Edit2 size={10} /> Override AI</button>
                 )}
               </div>
               
               {isEditingSynthesis ? (
                 <textarea 
                   disabled={isSaving}
                   value={editedValueProp}
                   onChange={(e) => setEditedValueProp(e.target.value)}
                   className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-blue-200 dark:border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[80px] disabled:opacity-50"
                 />
               ) : (
                 <p className="text-xs text-muted-foreground italic bg-slate-50 dark:bg-muted/30 p-3 rounded-xl border border-slate-200 dark:border-border/30">
                   {synthesis?.core_value_prop || "Awaiting asset analysis..."}
                 </p>
               )}
            </div>

            <div>
               <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Brand Tone</span>
               {isEditingSynthesis ? (
                 <textarea 
                   value={editedTone}
                   onChange={(e) => setEditedTone(e.target.value)}
                   className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-blue-200 dark:border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[60px]"
                 />
               ) : (
                 <p className="text-xs text-muted-foreground italic bg-slate-50 dark:bg-muted/30 p-3 rounded-xl border border-slate-200 dark:border-border/30">
                   {Array.isArray(synthesis?.identified_tone) ? synthesis.identified_tone.join(", ") : (synthesis?.identified_tone || "Awaiting asset analysis...")}
                 </p>
               )}
            </div>

            {(synthesis?.target_customer_profile || isEditingSynthesis) && (
              <div className="pt-6 border-t border-slate-100 dark:border-border/50">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Target Customer</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedTargetCustomer}
                    onChange={(e) => setEditedTargetCustomer(e.target.value)}
                    className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-blue-200 dark:border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[60px]"
                  />
                ) : (
                  <p className="text-xs text-muted-foreground italic bg-slate-50 dark:bg-muted/30 p-3 rounded-xl border border-slate-200 dark:border-border/30">
                    {synthesis.target_customer_profile}
                  </p>
                )}
              </div>
            )}

            {(synthesis?.key_differentiators?.length > 0 || isEditingSynthesis) && (
              <div className="pt-6 border-t border-slate-100 dark:border-border/50">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Key Differentiators {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedDifferentiators}
                    onChange={(e) => setEditedDifferentiators(e.target.value)}
                    className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-blue-200 dark:border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[80px]"
                    placeholder="Enter one differentiator per line..."
                  />
                ) : (
                  <div className="flex flex-row flex-wrap gap-2">
                    {synthesis.key_differentiators?.map((diff: string, i: number) => (
                      <span key={i} className="px-2 py-1 text-xs rounded-full bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border border-blue-100 dark:border-blue-500/20">
                        {diff}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {(synthesis?.proof_points?.length > 0 || isEditingSynthesis) && (
              <div className="pt-6 border-t border-slate-100 dark:border-border/50">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Proof Points {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedProofPoints}
                    onChange={(e) => setEditedProofPoints(e.target.value)}
                    className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-blue-200 dark:border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[80px]"
                    placeholder="Enter one proof point per line..."
                  />
                ) : (
                  <ul className="space-y-2">
                    {synthesis.proof_points?.map((pt: string, i: number) => (
                      <li key={i} className="text-xs text-muted-foreground italic bg-slate-50 dark:bg-muted/30 p-3 rounded-xl border border-slate-200 dark:border-border/30 flex items-start gap-2">
                        <span className="text-green-500 font-bold">✓</span> <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {(synthesis?.primary_pain_points_solved?.length > 0 || isEditingSynthesis) && (
              <div className="pt-6 border-t border-slate-100 dark:border-border/50">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Pain Points Solved {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedPainPoints}
                    onChange={(e) => setEditedPainPoints(e.target.value)}
                    className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-blue-200 dark:border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[80px]"
                    placeholder="Enter one pain point per line..."
                  />
                ) : (
                  <ul className="space-y-2">
                    {synthesis.primary_pain_points_solved?.map((pt: string, i: number) => (
                      <li key={i} className="text-xs text-muted-foreground italic bg-slate-50 dark:bg-muted/30 p-3 rounded-xl border border-slate-200 dark:border-border/30 flex items-start gap-2">
                        <span className="text-primary font-bold">→</span> <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* BANNED PHRASES UI */}
            {(synthesis?.banned_phrases?.length > 0 || isEditingSynthesis) && (
              <div className="pt-6 border-t border-slate-100 dark:border-border/50">
                <span className="text-[10px] font-bold text-red-500 uppercase tracking-widest block mb-2">Banned Phrases / Negative Constraints</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedBannedPhrases}
                    onChange={(e) => setEditedBannedPhrases(e.target.value)}
                    className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-red-200 dark:border-red-900/50 focus:outline-none focus:ring-1 focus:ring-red-500 min-h-[80px]"
                    placeholder="Enter phrases the AI should NEVER use (e.g. 'Hope this finds you well', 'synergy')..."
                  />
                ) : (
                  <div className="text-xs text-red-700 dark:text-red-400 italic bg-red-50 dark:bg-red-900/10 p-4 rounded-xl border border-red-100 dark:border-red-900/30">
                    {synthesis.banned_phrases}
                  </div>
                )}
              </div>
            )}

            {/* OBJECTION PLAYBOOK UI */}
            {(synthesis?.objection_playbook || isEditingSynthesis) && (
              <div className="pt-6 border-t border-slate-100 dark:border-border/50">
                <span className="text-[10px] font-bold text-purple-500 uppercase tracking-widest block mb-2">Objection Handling Playbook</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedObjectionPlaybook}
                    onChange={(e) => setEditedObjectionPlaybook(e.target.value)}
                    className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-purple-200 dark:border-purple-900/50 focus:outline-none focus:ring-1 focus:ring-purple-500 min-h-[120px]"
                    placeholder="How should the AI respond to negative intent? (e.g., 'If they say too expensive, pivot to our ROI case study...')"
                  />
                ) : (
                  <div className="text-xs text-purple-700 dark:text-purple-400 italic bg-purple-50 dark:bg-purple-900/10 p-4 rounded-xl border border-purple-100 dark:border-purple-900/30">
                    {synthesis.objection_playbook}
                  </div>
                )}
              </div>
            )}
            
            {isEditingSynthesis && (
              <div className="flex gap-2">
                <button onClick={() => setIsEditingSynthesis(false)} disabled={isSaving} className="flex-1 py-2 text-xs font-semibold text-muted-foreground bg-slate-100 dark:bg-muted rounded-xl hover:bg-slate-200 dark:hover:bg-muted/80 disabled:opacity-50">Cancel</button>
                <button onClick={handleSaveSynthesis} disabled={isSaving} className="flex-1 py-2 text-xs font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 shadow-sm disabled:opacity-50 flex items-center justify-center">
                  {isSaving ? <div className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" /> : 'Save Overrides'}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
