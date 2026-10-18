import { useState } from "react"
import { 
  BrainCircuit, FileText, LinkIcon, RefreshCw, Trash2, 
  Sparkles, Zap, ShieldCheck, CheckCircle2, AlertTriangle, ArrowRight, Lightbulb 
} from "lucide-react"
import type { KnowledgeAsset } from "./knowledge.types"
import { SYNTHESIS_STARTER_PRESETS } from "./SynthesisEditor"
import { fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

interface KnowledgeAssetListProps {
  assets: KnowledgeAsset[]
  onDelete: (id: string) => void
  onRetry: (id: string) => void
  mutateAssets?: () => void
  mutateSynthesis?: () => void
}

export function KnowledgeAssetList({ 
  assets, 
  onDelete, 
  onRetry,
  mutateAssets,
  mutateSynthesis 
}: KnowledgeAssetListProps) {
  const [loadingPresetId, setLoadingPresetId] = useState<string | null>(null)

  const handleApplyPreset = async (preset: typeof SYNTHESIS_STARTER_PRESETS[0]) => {
    try {
      setLoadingPresetId(preset.id)
      
      // 1. Update AI Synthesis
      const synthPayload = {
        core_value_prop: preset.valueProp,
        identified_tone: [preset.tone],
        target_customer_profile: preset.targetCustomer,
        key_differentiators: preset.differentiators.split("\n").filter(Boolean),
        proof_points: preset.proofPoints.split("\n").filter(Boolean),
        primary_pain_points_solved: preset.painPoints.split("\n").filter(Boolean),
        banned_phrases: preset.bannedPhrases,
        objection_playbook: preset.objectionPlaybook
      }

      await fetchWithAuth("/api/assets/knowledge/synthesis", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(synthPayload)
      })

      // 2. Upload text document as an asset in the knowledge base
      const textContent = `
Product & Company Synthesis: ${preset.title}
Core Value Prop: ${preset.valueProp}
Tone: ${preset.tone}
Target Customer: ${preset.targetCustomer}
Differentiators:
${preset.differentiators}
Proof Points:
${preset.proofPoints}
Pain Points Solved:
${preset.painPoints}
Objection Playbook:
${preset.objectionPlaybook}
      `.trim()

      await fetchWithAuth("/api/assets/knowledge/upload/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: `${preset.title} (Starter Knowledge)`,
          text: textContent
        })
      })

      toast.success(`Loaded "${preset.title}" into AI memory!`)
      if (mutateAssets) mutateAssets()
      if (mutateSynthesis) mutateSynthesis()

    } catch (err: any) {
      toast.error("Failed to load preset: " + (err.message || "Unknown error"))
    } finally {
      setLoadingPresetId(null)
    }
  }

  // ─── Area 4: Contextual Empty State with 1-Click Starter Presets ───
  if (assets.length === 0) {
    return (
      <div className="space-y-4 mt-4 text-left">
        <div className="p-6 rounded-xl border border-border/60 bg-muted/20 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <BrainCircuit size={20} />
              </div>
              <div>
                <h4 className="text-sm font-bold text-foreground">No Knowledge Sources Yet</h4>
                <p className="text-xs text-muted-foreground mt-0.5">
                  AI outreach converts 2.8x higher when grounded in real differentiators, proof points, and ICP pain points.
                </p>
              </div>
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shrink-0">
              Quick Start Available
            </span>
          </div>

          {/* 3 Quick-Start Presets */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
            {SYNTHESIS_STARTER_PRESETS.map((preset) => (
              <div
                key={preset.id}
                className="p-4 rounded-lg border border-border/60 bg-card hover:border-primary/40 transition-all flex flex-col justify-between shadow-xs"
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground">{preset.title}</span>
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground">
                      {preset.tag}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
                    {preset.summary}
                  </p>
                </div>

                <div className="pt-3">
                  <button
                    type="button"
                    disabled={loadingPresetId !== null}
                    onClick={() => handleApplyPreset(preset)}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary font-semibold text-xs transition-all disabled:opacity-50 cursor-pointer"
                  >
                    {loadingPresetId === preset.id ? (
                      <>
                        <RefreshCw size={12} className="animate-spin" />
                        <span>Loading...</span>
                      </>
                    ) : (
                      <>
                        <Zap size={12} />
                        <span>Load This Preset</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Pro-Tip Education Banner (Cake Equity Pattern) */}
          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-start gap-2.5 text-xs text-amber-900 dark:text-amber-200">
            <Lightbulb size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="leading-relaxed text-[11px]">
              <strong>Pro-Tip:</strong> If your company website is protected by Cloudflare anti-bot firewalls, loading one of the presets above or pasting raw homepage text gives the AI instant memory without scraper timeouts.
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ─── Active Asset List ───
  return (
    <div className="space-y-2.5 mt-4 text-left">
      {assets.map((asset) => (
        <div 
          key={asset.id || asset.name} 
          className="flex items-center justify-between p-3.5 rounded-lg border border-border/60 bg-card group hover:border-primary/30 transition-all shadow-xs"
        >
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-8 h-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
              {asset.type === 'pdf' ? (
                <FileText size={15} />
              ) : asset.type === 'text' ? (
                <FileText size={15} className="text-emerald-500" />
              ) : (
                <LinkIcon size={15} />
              )}
            </div>

            <div className="truncate">
              <p className="text-xs font-bold text-foreground truncate">{asset.name}</p>
              
              <div className="text-[11px] text-muted-foreground capitalize flex items-center gap-1.5 mt-0.5">
                <span>{asset.type === 'url' ? 'Website' : asset.type === 'pdf' ? 'PDF Document' : 'Text Note'}</span>
                <span>·</span>
                {asset.status === 'processing' ? (
                  <span className="text-primary font-semibold flex items-center gap-1">
                    <RefreshCw size={11} className="animate-spin" /> 
                    Vectorizing &amp; synthesizing embeddings...
                  </span>
                ) : asset.status === 'queued' ? (
                  <span className="text-amber-600 dark:text-amber-400 font-semibold flex items-center gap-1">
                    <RefreshCw size={11} /> 
                    Queued in processor
                  </span>
                ) : asset.status === 'failed' || asset.status === 'error' ? (
                  <span 
                    className="text-red-500 font-semibold inline-flex items-center gap-1 cursor-help"
                    title={asset.error_msg || "Processing failed. Click retry to re-scrape or index again."}
                  >
                    <AlertTriangle size={11} />
                    <span>Failed to process</span>
                    {asset.error_msg && (
                      <span className="text-[10px] text-red-400 font-normal max-w-[200px] truncate">
                        ({asset.error_msg})
                      </span>
                    )}
                  </span>
                ) : (
                  <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
                    <CheckCircle2 size={11} />
                    <span>Active in Vector Store</span>
                    {asset.chunk_count ? (
                      <span className="text-muted-foreground font-normal text-[10px]">
                        ({asset.chunk_count} chunks)
                      </span>
                    ) : null}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1">
            {(asset.status === 'failed' || asset.status === 'error') && (
              <button 
                type="button"
                onClick={() => onRetry(asset.id)}
                className="px-2 py-1 rounded-md bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400 text-xs font-semibold flex items-center gap-1 transition-colors"
                title="Retry processing"
                aria-label="Retry processing"
              >
                <RefreshCw size={12} />
                <span>Retry</span>
              </button>
            )}
            <button 
              type="button"
              onClick={() => onDelete(asset.id)}
              className="w-7 h-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
              title="Delete asset"
              aria-label="Delete asset"
            >
              <Trash2 size={13} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
