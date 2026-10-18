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
      <div className="h-full bg-card border border-border/60 rounded-xl p-6 lg:p-8 overflow-hidden relative shadow-xs">
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-muted/60 border border-border/60 flex items-center justify-center shadow-xs">
              <ElesiumLogo size={20} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">What the AI understood</h3>
              <p className="text-xs text-muted-foreground">Auto-generated from your content</p>
            </div>
          </div>

          <div className="space-y-6">
            {(synthesis?.is_draft || synthesis?.status === "pending_review") && (
              <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 flex flex-col gap-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                    <ElesiumLogo size={13} /> Draft Ready for Review
                  </span>
                  <button
                    type="button"
                    onClick={handleApproveSynthesis}
                    disabled={isApproving}
                    className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1 shadow-xs cursor-pointer"
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
                <span className={`font-bold ${
                  readinessScore >= 80 
                    ? 'text-emerald-600 dark:text-emerald-400' 
                    : readinessScore > 0 
                      ? 'text-amber-600 dark:text-amber-400' 
                      : 'text-muted-foreground'
                }`}>
                  {readinessScore >= 80 
                    ? 'Ready to write outreach' 
                    : readinessScore > 0 
                      ? `${readinessScore}% Grounded` 
                      : 'Needs Knowledge Input'}
                </span>
              </div>
              <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                <div 
                  className={`h-full transition-all duration-500 rounded-full ${
                    readinessScore >= 80 
                      ? 'bg-emerald-500' 
                      : readinessScore > 0 
                        ? 'bg-amber-500' 
                        : 'bg-transparent w-0'
                  }`}
                  style={{ width: `${readinessScore}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
                {readinessScore >= 80
                  ? "Your AI is grounded with verified differentiators and ready to personalize outreach sequences."
                  : readinessScore > 0
                    ? "Partially grounded. Add more company proof points and differentiators for highest response rates."
                    : "Without context, the AI writes generic emails. Add your website or documents on the left to calibrate."}
              </p>
            </div>

            {/* Empty State Callout without duplicating 3 full preset cards */}
            {!hasValueProp && !isEditingSynthesis && (
              <div className="p-4 rounded-xl bg-muted/30 border border-border/60 flex flex-col gap-2.5">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
                    <ElesiumLogo size={13} />
                  </div>
                  <h4 className="text-xs font-bold text-foreground">AI Knowledge Profile</h4>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Once you upload a document or link your website on the left, the AI will automatically synthesize your value proposition, tone, and customer personas here.
                </p>
              </div>
            )}
            
            <div className="pt-6 border-t border-border/60">
               <div className="flex justify-between items-center mb-2">
                 <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block">Core Value Prop</span>
                 {synthesis?.core_value_prop && !isEditingSynthesis && (
                   <button type="button" onClick={() => setIsEditingSynthesis(true)} className="text-[10px] text-primary hover:underline font-semibold flex items-center gap-1 cursor-pointer">
                     <ElesiumLogo size={11} /> Override AI
                   </button>
                 )}
               </div>
               
               {isEditingSynthesis ? (
                 <textarea 
                   disabled={isSaving}
                   value={editedValueProp}
                   onChange={(e) => setEditedValueProp(e.target.value)}
                   className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[80px] disabled:opacity-50"
                 />
               ) : (
                 <p className="text-xs text-muted-foreground italic bg-muted/20 p-3 rounded-lg border border-border/60">
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
                   className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[60px]"
                 />
               ) : (
                 <p className="text-xs text-muted-foreground italic bg-muted/20 p-3 rounded-lg border border-border/60">
                   {Array.isArray(synthesis?.identified_tone) ? synthesis.identified_tone.join(", ") : (synthesis?.identified_tone || "Awaiting asset analysis...")}
                 </p>
               )}
            </div>

            {(synthesis?.target_customer_profile || isEditingSynthesis) && (
              <div className="pt-6 border-t border-border/60">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Target Customer</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedTargetCustomer}
                    onChange={(e) => setEditedTargetCustomer(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[60px]"
                  />
                ) : (
                  <p className="text-xs text-muted-foreground italic bg-muted/20 p-3 rounded-lg border border-border/60">
                    {synthesis.target_customer_profile}
                  </p>
                )}
              </div>
            )}

            {(hasDifferentiators || isEditingSynthesis) && (
              <div className="pt-6 border-t border-border/60">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Key Differentiators {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedDifferentiators}
                    onChange={(e) => setEditedDifferentiators(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[80px]"
                    placeholder="Enter one differentiator per line..."
                  />
                ) : (
                  <div className="flex flex-row flex-wrap gap-2">
                    {synthesis?.key_differentiators?.map((diff: string, i: number) => (
                      <span key={i} className="px-2 py-1 text-xs rounded-md bg-primary/10 text-primary border border-primary/20">
                        {diff}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {(hasProofPoints || isEditingSynthesis) && (
              <div className="pt-6 border-t border-border/60">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Proof Points {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedProofPoints}
                    onChange={(e) => setEditedProofPoints(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[80px]"
                    placeholder="Enter one proof point per line..."
                  />
                ) : (
                  <ul className="space-y-2">
                    {synthesis?.proof_points?.map((pt: string, i: number) => (
                      <li key={i} className="text-xs text-muted-foreground italic bg-muted/20 p-3 rounded-lg border border-border/60 flex items-start gap-2">
                        <Check size={13} className="text-emerald-500 shrink-0 mt-0.5" /> <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {(synthesis?.primary_pain_points_solved?.length > 0 || isEditingSynthesis) && (
              <div className="pt-6 border-t border-border/60">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest block mb-2">Pain Points Solved {isEditingSynthesis && "(One per line)"}</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedPainPoints}
                    onChange={(e) => setEditedPainPoints(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[80px]"
                    placeholder="Enter one pain point per line..."
                  />
                ) : (
                  <ul className="space-y-2">
                    {synthesis.primary_pain_points_solved?.map((pt: string, i: number) => (
                      <li key={i} className="text-xs text-muted-foreground italic bg-muted/20 p-3 rounded-lg border border-border/60 flex items-start gap-2">
                        <span className="text-primary font-bold">→</span> <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* BANNED PHRASES UI */}
            {(synthesis?.banned_phrases?.length > 0 || isEditingSynthesis) && (
              <div className="pt-6 border-t border-border/60">
                <span className="text-[10px] font-bold text-destructive uppercase tracking-widest block mb-2">Banned Phrases / Negative Constraints</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedBannedPhrases}
                    onChange={(e) => setEditedBannedPhrases(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-destructive/40 focus:outline-none focus:ring-1 focus:ring-destructive min-h-[80px]"
                    placeholder="Enter phrases the AI should NEVER use (e.g. 'Hope this finds you well', 'synergy')..."
                  />
                ) : (
                  <div className="text-xs text-destructive italic bg-destructive/10 p-4 rounded-lg border border-destructive/20">
                    {synthesis.banned_phrases}
                  </div>
                )}
              </div>
            )}

            {/* OBJECTION PLAYBOOK UI */}
            {(synthesis?.objection_playbook || isEditingSynthesis) && (
              <div className="pt-6 border-t border-border/60">
                <span className="text-[10px] font-bold text-primary uppercase tracking-widest block mb-2">Objection Handling Playbook</span>
                {isEditingSynthesis ? (
                  <textarea 
                    disabled={isSaving}
                    value={editedObjectionPlaybook}
                    onChange={(e) => setEditedObjectionPlaybook(e.target.value)}
                    className="w-full text-xs text-foreground bg-background p-3 rounded-lg border border-border focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[120px]"
                    placeholder="How should the AI respond to negative intent? (e.g., 'If they say too expensive, pivot to our ROI case study...')"
                  />
                ) : (
                  <div className="text-xs text-foreground italic bg-muted/20 p-4 rounded-lg border border-border/60">
                    {synthesis.objection_playbook}
                  </div>
                )}
              </div>
            )}
            
            {isEditingSynthesis && (
              <div className="flex gap-2">
                <button type="button" onClick={() => setIsEditingSynthesis(false)} disabled={isSaving} className="flex-1 py-2 text-xs font-semibold text-muted-foreground bg-muted hover:bg-muted/80 rounded-lg disabled:opacity-50 cursor-pointer transition-colors">Cancel</button>
                <button type="button" onClick={handleSaveSynthesis} disabled={isSaving} className="flex-1 py-2 text-xs font-semibold text-primary-foreground bg-primary hover:bg-primary/90 rounded-lg shadow-xs disabled:opacity-50 flex items-center justify-center cursor-pointer transition-colors">
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
