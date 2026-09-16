import { BrainCircuit, FileText, LinkIcon, RefreshCw, Trash2 } from "lucide-react"
import type { KnowledgeAsset } from "./knowledge.types"

interface KnowledgeAssetListProps {
  assets: KnowledgeAsset[]
  onDelete: (id: string) => void
  onRetry: (id: string) => void
}

export function KnowledgeAssetList({ assets, onDelete, onRetry }: KnowledgeAssetListProps) {
  if (assets.length === 0) {
    return (
      <div className="py-12 flex flex-col items-center justify-center text-center border-2 border-dashed border-slate-200 dark:border-border/50 rounded-3xl bg-slate-50/50 dark:bg-muted/5 mt-4">
        <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-muted flex items-center justify-center mb-4">
          <BrainCircuit className="text-muted-foreground/40 w-6 h-6" />
        </div>
        <p className="text-sm font-semibold text-foreground">The AI doesn't know anything yet</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-xs">Add your website, a PDF, or paste some text above — the AI will learn from it instantly.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2 mt-4">
      {assets.map((asset) => (
        <div key={asset.id || asset.name} className="flex items-center justify-between p-3.5 rounded-2xl border border-slate-200 dark:border-border/50 bg-slate-50 dark:bg-muted/10 group hover:border-blue-200 dark:hover:border-blue-800/50 transition-colors">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-8 h-8 rounded-lg bg-blue-100/50 dark:bg-blue-900/30 flex items-center justify-center shrink-0">
              {asset.type === 'pdf' ? <FileText size={14} className="text-blue-600 dark:text-blue-400" /> : asset.type === 'text' ? <FileText size={14} className="text-green-600 dark:text-green-400" /> : <LinkIcon size={14} className="text-blue-600 dark:text-blue-400" />}
            </div>
            <div className="truncate">
              <p className="text-sm font-medium text-foreground truncate">{asset.name}</p>
              <p className="text-xs text-muted-foreground capitalize flex items-center gap-1">
                {asset.type === 'url' ? 'Website' : asset.type === 'pdf' ? 'Document' : 'Pasted text'} · {
                  asset.status === 'processing' ? <span className="text-amber-500 font-medium flex items-center gap-1"><RefreshCw size={10} className="animate-spin" /> Processing...</span>
                  : asset.status === 'failed' ? <span className="text-red-500 font-medium">Failed to process</span>
                  : <span className="text-green-500 font-medium">Active</span>
                }
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {asset.status === 'failed' && (
              <button 
                onClick={() => onRetry(asset.id)}
                className="w-8 h-8 flex items-center justify-center rounded-lg text-amber-600 hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
                title="Retry processing"
              >
                <RefreshCw size={14} />
              </button>
            )}
            <button 
              onClick={() => onDelete(asset.id)}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
              title="Delete asset"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
