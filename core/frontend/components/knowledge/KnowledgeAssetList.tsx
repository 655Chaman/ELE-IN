import { useState } from "react"
import { 
  FileText, LinkIcon, RefreshCw, Trash2, 
  Sparkles, CheckCircle2, AlertTriangle, ArrowRight
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

  // ─── Minimalist Contextual Empty State ───
  if (assets.length === 0) {
    return (
      <div className="py-8 px-6 rounded-xl border border-dashed border-border/60 bg-muted/10 text-center space-y-3">
        <div className="w-9 h-9 rounded-lg bg-muted/40 border border-border/40 text-muted-foreground flex items-center justify-center mx-auto">
          <FileText size={16} />
        </div>
        <div>
          <h4 className="text-xs font-medium text-foreground">No Knowledge Sources Added Yet</h4>
          <p className="text-[11px] text-muted-foreground mt-0.5 max-w-sm mx-auto">
            Connect your company website or upload a document above so outreach cites real proof points instead of generic templates.
          </p>
        </div>

        {/* Minimalist Starter Chips */}
        <div className="pt-2 flex flex-wrap items-center justify-center gap-2">
          <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">Or start with a template:</span>
          {SYNTHESIS_STARTER_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              disabled={loadingPresetId !== null}
              onClick={() => handleApplyPreset(preset)}
              className="px-2.5 py-1 rounded-md text-[11px] font-medium border border-border/60 bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
            >
              {loadingPresetId === preset.id ? (
                <>
                  <RefreshCw size={10} className="animate-spin" />
                  <span>Loading...</span>
                </>
              ) : (
                <span>{preset.title.split("&")[0].trim()}</span>
              )}
            </button>
          ))}
        </div>
      </div>
    )
  }

  // ─── Active Asset List ───
  return (
    <div className="space-y-2 text-left">
      {assets.map((asset) => (
        <div 
          key={asset.id || asset.name} 
          className="flex items-center justify-between p-3 rounded-lg border border-border/50 bg-card/50 hover:bg-card hover:border-border/80 transition-colors"
        >
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-7 h-7 rounded-md bg-muted/60 border border-border/40 text-foreground/70 flex items-center justify-center shrink-0">
              {asset.type === 'pdf' ? (
                <FileText size={14} />
              ) : asset.type === 'text' ? (
                <FileText size={14} />
              ) : (
                <LinkIcon size={14} />
              )}
            </div>

            <div className="truncate">
              <p className="text-xs font-medium text-foreground truncate">{asset.name}</p>
              
              <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                <span>{asset.type === 'url' ? 'Website' : asset.type === 'pdf' ? 'PDF' : 'Notes'}</span>
                <span>·</span>
                {asset.status === 'processing' ? (
                  <span className="text-foreground font-medium flex items-center gap-1">
                    <RefreshCw size={10} className="animate-spin text-muted-foreground" /> 
                    Indexing...
                  </span>
                ) : asset.status === 'queued' ? (
                  <span className="text-amber-500 font-medium flex items-center gap-1">
                    <RefreshCw size={10} /> 
                    Queued
                  </span>
                ) : asset.status === 'failed' || asset.status === 'error' ? (
                  <span 
                    className="text-destructive font-medium inline-flex items-center gap-1 cursor-help"
                    title={asset.error_msg || "Processing failed. Click retry to re-scrape."}
                  >
                    <AlertTriangle size={11} />
                    <span>Failed to process</span>
                  </span>
                ) : (
                  <span className="text-muted-foreground flex items-center gap-1">
                    <CheckCircle2 size={11} className="text-foreground/70" />
                    <span>Indexed</span>
                    {asset.chunk_count ? (
                      <span className="text-muted-foreground/60 text-[10px]">
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
                className="px-2 py-1 rounded-md border border-border/60 hover:bg-muted text-xs font-medium flex items-center gap-1 transition-colors"
                title="Retry processing"
                aria-label="Retry processing"
              >
                <RefreshCw size={11} />
                <span>Retry</span>
              </button>
            )}
            <button 
              type="button"
              onClick={() => onDelete(asset.id)}
              className="w-7 h-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
              title="Delete source"
              aria-label="Delete source"
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
