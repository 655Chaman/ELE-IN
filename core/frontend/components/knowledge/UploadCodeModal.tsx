import { useState, useRef } from "react"
import { Cpu, Terminal, Shield, UploadCloud, FileCode2, Binary, Lock, CheckCircle2, AlertCircle } from "lucide-react"
import { toast } from "sonner"
import { friendlyToast } from "../FriendlyError"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import { cn } from "@/lib/utils"
import useSWR from "swr"

const ALLOWED_EXTENSIONS = [".js", ".mjs", ".ts", ".wasm", ".zip", ".crx", ".json"]

export function UploadCodeModal({ mutateAssets }: { mutateAssets: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const { openPaywall } = usePaywall()

  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher)
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'
  const maxAssets = isPro ? (tier === 'ENTERPRISE' ? 100 : 25) : 3

  const { data: assets } = useSWR<any[]>('/api/assets/knowledge/assets', fetcher)
  const currentCount = Array.isArray(assets) ? assets.length : 0
  const isCapped = !isPro && currentCount >= maxAssets

  const handleZoneClick = () => {
    if (isUploading) return
    if (isCapped) {
      openPaywall({ featureName: "Deep Code & Wasm Knowledge Engine" })
      toast.info(`Free plan limit reached (${currentCount}/${maxAssets} sources). Upgrade to Growth Pro to ingest full technical codebases.`)
      return
    }
    fileInputRef.current?.click()
  }

  const uploadCodeFile = async (file: File) => {
    if (isCapped) {
      openPaywall({ featureName: "Deep Code & Wasm Knowledge Engine" })
      toast.info(`Free plan limit reached (${currentCount}/${maxAssets} sources). Upgrade to Growth Pro to ingest technical codebases.`)
      return
    }

    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      toast.error(`Unsupported file type '${ext}'. Please upload .js, .ts, .wasm, .zip, or .crx artifacts.`)
      return
    }

    if (file.size > 25 * 1024 * 1024) {
      toast.error("File exceeds maximum allowed size of 25MB.")
      return
    }

    setIsUploading(true)

    try {
      const formData = new FormData()
      formData.append("file", file)

      const res = await fetchWithAuth("/api/assets/knowledge/upload/code", {
        method: "POST",
        body: formData
      })

      if (!res.ok) {
        if (res.status === 403) {
          openPaywall({ featureName: "Deep Code & Wasm Knowledge Engine" })
          toast.info("Knowledge Base limit reached. Upgrade to Growth Pro for up to 25 sources.")
          return
        }
        const errorText = await res.text()
        let detail = errorText
        try {
          const parsed = JSON.parse(errorText)
          detail = parsed.detail || detail
        } catch (_) {}
        throw new Error(detail)
      }

      toast.success(`Queued ${file.name} for REA & Ghidra technical decompilation!`)
      mutateAssets()
    } catch (e: any) {
      friendlyToast('Failed to upload technical artifact — please try again.', e)
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    uploadCodeFile(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (isUploading) return
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    uploadCodeFile(file)
  }

  return (
    <div className="space-y-6">
      {/* ── Capabilities Header Cards ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-left">
        <div className="p-3.5 rounded-xl border border-border/50 bg-card/40 flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-500 flex items-center justify-center shrink-0">
            <Terminal size={15} />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-foreground">morluto/REA AST Analysis</h4>
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
              Extracts ground-truth frameworks, API route topologies, and UI workflow routes from minified bundles.
            </p>
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-border/50 bg-card/40 flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-500 flex items-center justify-center shrink-0">
            <Binary size={15} />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-foreground">Ghidra 12.2 Wasm Decompiler</h4>
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
              Disassembles WebAssembly bytecode and linear memory to uncover canvas hashes and mouse kinematic formulas.
            </p>
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-border/50 bg-card/40 flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 flex items-center justify-center shrink-0">
            <Shield size={15} />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-foreground">Zero-Secret Vector Sanitization</h4>
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
              EPF Layer 2 regex scrubber masks API keys, JWTs, and database credentials before vector embedding.
            </p>
          </div>
        </div>
      </div>

      {/* ── Dropzone Area ── */}
      <div
        role="button"
        tabIndex={isUploading ? -1 : 0}
        onClick={handleZoneClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            handleZoneClick()
          }
        }}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={cn(
          "relative group border border-dashed rounded-xl p-8 text-center transition-all cursor-pointer flex flex-col items-center justify-center gap-3 overflow-hidden",
          isDragging 
            ? "border-cyan-500 bg-cyan-500/5 ring-2 ring-cyan-500/20" 
            : isCapped 
            ? "border-border/40 bg-muted/5 opacity-80" 
            : "border-border/60 hover:border-border hover:bg-muted/10",
          isUploading && "pointer-events-none opacity-60"
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".js,.mjs,.ts,.wasm,.zip,.crx,.json"
          onChange={handleFileUpload}
          disabled={isUploading}
          className="hidden"
          aria-label="Upload code intelligence artifact"
        />

        <div className={cn(
          "w-11 h-11 rounded-xl flex items-center justify-center transition-colors border",
          isDragging 
            ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-500" 
            : "bg-muted/50 border-border/50 text-muted-foreground group-hover:text-foreground"
        )}>
          {isCapped ? (
            <Lock size={18} className="text-amber-500" />
          ) : isUploading ? (
            <div className="w-5 h-5 rounded-full border-2 border-cyan-500 border-t-transparent animate-spin" />
          ) : (
            <Cpu size={18} />
          )}
        </div>

        <div className="space-y-1 max-w-sm">
          <p className="text-xs font-semibold text-foreground">
            {isUploading ? "Uploading & Analyzing Artifact..." : isCapped ? "Code Intelligence Storage Capped" : "Upload Code Artifact or Binary"}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {isCapped 
              ? `You've reached the free tier limit of ${maxAssets} sources. Upgrade to Growth Pro to ingest technical codebases.`
              : "Drag & drop web bundles (.js, .ts), WebAssembly binaries (.wasm), or Chrome Extensions (.crx, .zip)"}
          </p>
        </div>

        <div className="flex items-center gap-2 pt-1 text-[10px] text-muted-foreground font-mono">
          <span className="px-2 py-0.5 rounded-md bg-muted/60 border border-border/40">.wasm</span>
          <span className="px-2 py-0.5 rounded-md bg-muted/60 border border-border/40">.zip / .crx</span>
          <span className="px-2 py-0.5 rounded-md bg-muted/60 border border-border/40">.js / .ts</span>
          <span>·</span>
          <span>Max 25MB</span>
        </div>
      </div>
    </div>
  )
}
