import { Edit2, Sparkles, Check, ArrowRight, Zap, ShieldCheck } from "lucide-react";
import { ElesiumLogo } from "@/components/ElesiumLogo";
import { toast } from "sonner";
import { useSynthesisForm } from "./hooks/useSynthesisForm";

export const SYNTHESIS_STARTER_PRESETS = [
  {
    id: "saas",
    title: "B2B SaaS & Tech Product",
    tag: "High Converting",
    summary: "Automated pipeline, ROI-focused, zero spam, consultative tone",
    valueProp: "We help B2B teams automate multichannel outbound, turning cold prospects into qualified pipeline without burning domains.",
    tone: "Consultative, crisp, technical-yet-accessible, zero sales fluff",
    targetCustomer: "VP of Sales, Head of Growth, Founders at 10-250 person software companies",
    differentiators: "Anti-spam warmup algorithm with zero domain burn\nMulti-account sender load balancing\nDeep knowledge-base grounding",
    proofPoints: "Over 1.2M outreach touchpoints executed safely\nAvg 42% reply rate on calibrated sequences\n99.8% account safety score",
    painPoints: "Burnt secondary domains and low deliverability\nTime wasted sending generic template emails that get flagged as spam\nManual follow-up fatigue",
    bannedPhrases: "Hope this email finds you well, synergistic, circle back, bumping this to the top of your inbox",
    objectionPlaybook: "If they say 'Not interested': Acknowledge warmly and ask if they are currently solving outbound in-house or using another tool.\nIf they say 'Too busy': Ask if sending a 2-minute video overview would be less friction."
  },
  {
    id: "agency",
    title: "Growth Agency & SDR Services",
    tag: "ROI Driven",
    summary: "Done-for-you lead generation, booked calls, high status tone",
    valueProp: "We build and operate custom LinkedIn client acquisition engines for boutique consulting and agencies.",
    tone: "Executive, authoritative, ROI-focused, high status peer-to-peer",
    targetCustomer: "Managing Partners, Agency Owners, Boutique Consultancies doing $500k-$5M ARR",
    differentiators: "Guaranteed qualified executive meetings\nTailored ICP research and custom message sequences\nZero internal team overhead required",
    proofPoints: "Consistent 15-25 qualified executive calls booked per month for client partners",
    painPoints: "Inconsistent referral rollercoaster\nSDR turnover and expensive training cycles\nStruggling to reach enterprise buyers on LinkedIn",
    bannedPhrases: "Quick question, synergy, revolutionary, let's grab coffee",
    objectionPlaybook: "If they say 'We have an SDR': Highlight that we augment existing reps with targeted executive account lists.\nIf they say 'Send more info': Send 1 concise case study showing 3x pipeline growth in 60 days."
  },
  {
    id: "services",
    title: "Specialized Tech & Engineering",
    tag: "Peer Tone",
    summary: "Pre-vetted engineering squads, technical peer tone, direct problem-solving",
    valueProp: "We provide senior-level engineering talent and specialized software squads to accelerate mission-critical product roadmaps.",
    tone: "Engineering-first, authentic, candid, zero sales-speak",
    targetCustomer: "CTOs, VP of Engineering, Technical Co-founders with open engineering headcount",
    differentiators: "Top 1% pre-vetted senior engineers\n2-week risk-free trial period before commitment\nDirect overlap with US and European timezones",
    proofPoints: "Zero unplanned attrition across key client production teams in 2025",
    painPoints: "Months spent interviewing candidates who fail technical screens\nMissed roadmap delivery deadlines\nProhibitive local hiring costs",
    bannedPhrases: "Synergy, disruptive, rockstar developer, ninja coder",
    objectionPlaybook: "If they say 'We only hire local': Offer our 2-week risk-free trial so they can evaluate code quality directly in PRs."
  }
];

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
    isSaving,
    handleApproveSynthesis,
    isApproving
  } = useSynthesisForm(synthesis, mutateSynthesis);

  const handleLoadPreset = (preset: typeof SYNTHESIS_STARTER_PRESETS[0]) => {
    setEditedValueProp(preset.valueProp);
    setEditedTone(preset.tone);
    setEditedTargetCustomer(preset.targetCustomer);
    setEditedDifferentiators(preset.differentiators);
    setEditedProofPoints(preset.proofPoints);
    setEditedPainPoints(preset.painPoints);
    setEditedBannedPhrases(preset.bannedPhrases);
    setEditedObjectionPlaybook(preset.objectionPlaybook);
    setIsEditingSynthesis(true);
    toast.success(`Loaded "${preset.title}" preset — review below and click "Save Overrides" to lock in`);
  };

  return (
    <div className="md:col-span-1 group outline-none">
      <div className="h-full bg-white dark:bg-card/40 border border-slate-200 dark:border-border/50 rounded-[40px] p-8 overflow-hidden relative shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-2xl">
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-6">

            <div className="w-10 h-10 rounded-xl bg-muted/60 border border-border flex items-center justify-center shadow-xs">
              <ElesiumLogo size={20} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">What the AI understood</h3>
              <p className="text-xs text-muted-foreground">Auto-generated from your content</p>
            </div>
          </div>

          <div className="space-y-6">
            {(synthesis?.is_draft || synthesis?.status === "pending_review") && (
              <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col gap-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                    <ElesiumLogo size={13} /> Draft Ready for Review
                  </span>
                  <button
                    onClick={handleApproveSynthesis}
                    disabled={isApproving}
                    className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1 shadow-sm"
                  >
                    {isApproving ? "Locking in..." : "Approve & Lock In"}
                  </button>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Generated from your documents. Review the values below and click "Approve & Lock In" to make this the active constitution for all automated outreach.
                </p>
              </div>
            )}
            <div>
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <ElesiumLogo size={13} />
                  <span>AI Readiness</span>
                </span>
                <span className={`font-bold ${synthesis?.core_value_prop || isEditingSynthesis ? 'text-green-600 dark:text-green-500' : 'text-orange-600 dark:text-primary'}`}>
                  {synthesis?.core_value_prop || isEditingSynthesis ? 'Ready to write DMs' : 'Add content or pick preset'}
                </span>
              </div>
              <div className="h-2 w-full bg-slate-100 dark:bg-muted rounded-full overflow-hidden">
                <div className={`h-full transition-all duration-700 ${synthesis?.core_value_prop || isEditingSynthesis ? 'bg-green-500 w-full' : 'bg-primary w-[15%]'}`} />
              </div>
              <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
                {synthesis?.core_value_prop || isEditingSynthesis
                  ? "Your AI will write DMs that specifically reference your product's benefits and your company's unique angle — not generic filler."
                  : "Without context, the AI writes generic emails. Add your website above or load a proven industry constitution below."}
              </p>
            </div>

            {/* Quick-Start Presets for cold-start (Transcript 2: Goal Gradient Effect) */}
            {!synthesis?.core_value_prop && !isEditingSynthesis && (
              <div className="p-4 rounded-2xl bg-primary/5 border border-primary/20 flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                    <ElesiumLogo size={13} />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-foreground">Or Launch with a Proven Profile</h4>
                    <p className="text-[11px] text-muted-foreground">Pick your model to pre-seed value prop, voice, and rules in 1 click:</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-2 pt-1">
                  {SYNTHESIS_STARTER_PRESETS.map(preset => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => handleLoadPreset(preset)}
                      className="p-3 rounded-xl border border-border/70 bg-card hover:border-primary/50 hover:bg-primary/5 transition-all text-left group flex items-start justify-between cursor-pointer"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-foreground group-hover:text-primary transition-colors">
                            {preset.title}
                          </span>
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                            {preset.tag}
                          </span>
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-1 line-clamp-1">
                          {preset.summary}
                        </p>
                      </div>
                      <span className="text-[11px] font-semibold text-primary opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-2 mt-0.5">
                        Load &rarr;
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            
            <div className="pt-6 border-t border-slate-100 dark:border-border/50">
               <div className="flex justify-between items-center mb-2">
                 <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block">Core Value Prop</span>
                 {synthesis?.core_value_prop && !isEditingSynthesis && (
                   <button onClick={() => setIsEditingSynthesis(true)} className="text-[10px] text-blue-500 hover:text-blue-600 font-semibold flex items-center gap-1"><ElesiumLogo size={11} /> Override AI</button>
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
                        <Check size={13} className="text-emerald-500 shrink-0 mt-0.5" /> <span>{pt}</span>
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
                <span className="text-[10px] font-bold text-blue-500 uppercase tracking-widest block mb-2">Objection Handling Playbook</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedObjectionPlaybook}
                    onChange={(e) => setEditedObjectionPlaybook(e.target.value)}
                    className="w-full text-xs text-foreground bg-white dark:bg-background p-3 rounded-xl border border-blue-200 dark:border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[120px]"
                    placeholder="How should the AI respond to negative intent? (e.g., 'If they say too expensive, pivot to our ROI case study...')"
                  />
                ) : (
                  <div className="text-xs text-blue-700 dark:text-blue-400 italic bg-blue-50 dark:bg-blue-900/10 p-4 rounded-xl border border-blue-100 dark:border-blue-900/30">
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
