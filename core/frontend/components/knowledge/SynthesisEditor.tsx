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

  const hasValueProp = Boolean(synthesis?.core_value_prop || (isEditingSynthesis && editedValueProp.trim()));
  const hasTargetCustomer = Boolean(synthesis?.target_customer_profile || (isEditingSynthesis && editedTargetCustomer.trim()));
  const hasDifferentiators = Boolean(
    (Array.isArray(synthesis?.key_differentiators) && synthesis.key_differentiators.length > 0) ||
    (isEditingSynthesis && editedDifferentiators.trim())
  );
  const hasProofPoints = Boolean(
    (Array.isArray(synthesis?.proof_points) && synthesis.proof_points.length > 0) ||
    (isEditingSynthesis && editedProofPoints.trim())
  );

  // Accurate multi-factor readiness score
  let readinessScore = 0;
  if (hasValueProp) readinessScore += 30;
  if (hasTargetCustomer) readinessScore += 25;
  if (hasDifferentiators) readinessScore += 25;
  if (hasProofPoints) readinessScore += 20;

  return (
    <div className="lg:col-span-1 group outline-none">
      <div className="h-full bg-card/40 border border-border/50 rounded-xl p-6 lg:p-7 overflow-hidden relative">
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shadow-2xs">
              <ElesiumLogo size={16} />
            </div>
            <div>
              <h3 className="text-sm font-medium text-foreground">AI Understanding</h3>
              <p className="text-xs text-muted-foreground">What the AI learned from your sources</p>
            </div>
          </div>

          <div className="space-y-5">
            {(synthesis?.is_draft || synthesis?.status === "pending_review") && (
              <div className="p-3 rounded-lg bg-muted/40 border border-border/60 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-foreground flex items-center gap-1.5">
                    <Sparkles size={13} className="text-muted-foreground" />
                    <span>Draft Ready for Review</span>
                  </span>
                  <button
                    type="button"
                    onClick={handleApproveSynthesis}
                    disabled={isApproving}
                    className="px-2.5 py-1 bg-foreground text-background hover:bg-foreground/90 rounded-md text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {isApproving ? "Locking in..." : "Approve"}
                  </button>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Review values extracted from your sources and click Approve to lock in for outreach.
                </p>
              </div>
            )}

            <div className="space-y-1.5 pb-2 border-b border-border/40">
              <div className="flex justify-between items-center text-xs">
                <span className="text-muted-foreground text-[11px] uppercase tracking-wider font-medium">Calibrated Context</span>
                <span className="font-mono text-xs text-foreground font-medium">
                  {readinessScore >= 80 ? "Calibrated" : readinessScore > 0 ? `${readinessScore}%` : "Awaiting Sources"}
                </span>
              </div>
              <div className="h-1 w-full bg-muted/60 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-foreground transition-all duration-500 rounded-full"
                  style={{ width: `${readinessScore}%` }}
                />
              </div>
            </div>

            {!hasValueProp && !isEditingSynthesis && (
              <p className="text-xs text-muted-foreground leading-relaxed">
                Add your website or upload a document on the left. The AI will extract and structure your core value proposition, tone, and proof points here so outreach cites real data.
              </p>
            )}
            
            <div className="pt-2">
               <div className="flex justify-between items-center mb-1.5">
                 <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">Core Value Prop</span>
                 {synthesis?.core_value_prop && !isEditingSynthesis && (
                   <button type="button" onClick={() => setIsEditingSynthesis(true)} className="text-[10px] text-muted-foreground hover:text-foreground font-medium flex items-center gap-1 cursor-pointer">
                     <Edit2 size={11} /> Edit
                   </button>
                 )}
               </div>
               
               {isEditingSynthesis ? (
                 <textarea 
                   disabled={isSaving}
                   value={editedValueProp}
                   onChange={(e) => setEditedValueProp(e.target.value)}
                   className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[80px] disabled:opacity-50"
                 />
               ) : (
                 <p className="text-xs text-foreground/80 bg-muted/20 p-3 rounded-lg border border-border/40 leading-relaxed font-normal">
                   {synthesis?.core_value_prop || <span className="text-muted-foreground/60">Awaiting company sources...</span>}
                 </p>
               )}
            </div>

            <div>
               <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Brand Tone</span>
               {isEditingSynthesis ? (
                 <textarea 
                   value={editedTone}
                   onChange={(e) => setEditedTone(e.target.value)}
                   className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[60px]"
                 />
               ) : (
                 <p className="text-xs text-foreground/80 bg-muted/20 p-3 rounded-lg border border-border/40 leading-relaxed font-normal">
                   {Array.isArray(synthesis?.identified_tone) ? synthesis.identified_tone.join(", ") : (synthesis?.identified_tone || <span className="text-muted-foreground/60">Awaiting company sources...</span>)}
                 </p>
               )}
            </div>

            {(synthesis?.target_customer_profile || isEditingSynthesis) && (
              <div className="pt-4 border-t border-border/40">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Target Customer</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedTargetCustomer}
                    onChange={(e) => setEditedTargetCustomer(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[60px]"
                  />
                ) : (
                  <p className="text-xs text-foreground/80 bg-muted/20 p-3 rounded-lg border border-border/40 leading-relaxed font-normal">
                    {synthesis.target_customer_profile}
                  </p>
                )}
              </div>
            )}

            {(hasDifferentiators || isEditingSynthesis) && (
              <div className="pt-4 border-t border-border/40">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Key Differentiators {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedDifferentiators}
                    onChange={(e) => setEditedDifferentiators(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[80px]"
                    placeholder="Enter one differentiator per line..."
                  />
                ) : (
                  <div className="flex flex-row flex-wrap gap-1.5">
                    {synthesis?.key_differentiators?.map((diff: string, i: number) => (
                      <span key={i} className="px-2 py-0.5 text-xs rounded-md bg-muted/50 text-foreground/90 border border-border/50">
                        {diff}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {(hasProofPoints || isEditingSynthesis) && (
              <div className="pt-4 border-t border-border/40">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Proof Points {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedProofPoints}
                    onChange={(e) => setEditedProofPoints(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[80px]"
                    placeholder="Enter one proof point per line..."
                  />
                ) : (
                  <ul className="space-y-1.5">
                    {synthesis?.proof_points?.map((pt: string, i: number) => (
                      <li key={i} className="text-xs text-foreground/80 bg-muted/20 p-2.5 rounded-lg border border-border/40 flex items-start gap-2">
                        <Check size={13} className="text-muted-foreground shrink-0 mt-0.5" /> <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {(synthesis?.primary_pain_points_solved?.length > 0 || isEditingSynthesis) && (
              <div className="pt-4 border-t border-border/40">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Pain Points Solved {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedPainPoints}
                    onChange={(e) => setEditedPainPoints(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[80px]"
                    placeholder="Enter one pain point per line..."
                  />
                ) : (
                  <ul className="space-y-1.5">
                    {synthesis.primary_pain_points_solved?.map((pt: string, i: number) => (
                      <li key={i} className="text-xs text-foreground/80 bg-muted/20 p-2.5 rounded-lg border border-border/40 flex items-start gap-2">
                        <span className="text-muted-foreground font-mono">→</span> <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* BANNED PHRASES UI */}
            {(synthesis?.banned_phrases?.length > 0 || isEditingSynthesis) && (
              <div className="pt-4 border-t border-border/40">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Banned Phrases</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedBannedPhrases}
                    onChange={(e) => setEditedBannedPhrases(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[80px]"
                    placeholder="Enter phrases the AI should never use..."
                  />
                ) : (
                  <div className="text-xs text-muted-foreground/90 bg-muted/20 p-3 rounded-lg border border-border/40">
                    {synthesis.banned_phrases}
                  </div>
                )}
              </div>
            )}

            {/* OBJECTION PLAYBOOK UI */}
            {(synthesis?.objection_playbook || isEditingSynthesis) && (
              <div className="pt-4 border-t border-border/40">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Objection Handling Playbook</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedObjectionPlaybook}
                    onChange={(e) => setEditedObjectionPlaybook(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border/70 focus:outline-none focus:border-foreground/40 min-h-[100px]"
                    placeholder="How should the AI respond to negative intent?..."
                  />
                ) : (
                  <div className="text-xs text-foreground/80 bg-muted/20 p-3 rounded-lg border border-border/40">
                    {synthesis.objection_playbook}
                  </div>
                )}
              </div>
            )}
            
            {isEditingSynthesis && (
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setIsEditingSynthesis(false)} disabled={isSaving} className="flex-1 py-1.5 text-xs font-medium text-muted-foreground bg-muted hover:bg-muted/80 rounded-lg disabled:opacity-50 cursor-pointer transition-colors">Cancel</button>
                <button type="button" onClick={handleSaveSynthesis} disabled={isSaving} className="flex-1 py-1.5 text-xs font-medium text-background bg-foreground hover:bg-foreground/90 rounded-lg disabled:opacity-50 flex items-center justify-center cursor-pointer transition-colors">
                  {isSaving ? <div className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" /> : "Save Changes"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
