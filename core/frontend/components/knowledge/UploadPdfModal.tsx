import { UploadCloud, Lock, Info } from "lucide-react"
import { toast } from "sonner"
import { friendlyToast } from "../FriendlyError"
import { useRef, useState } from "react"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import { cn } from "@/lib/utils"
import useSWR from "swr"

export function UploadPdfModal({ mutateAssets }: { mutateAssets: () => void }) {
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
      openPaywall({ featureName: "Knowledge Base Storage" })
      toast.info(`Free plan limit reached (${currentCount}/${maxAssets} documents). Upgrade to Growth Pro to upload up to 25 documents.`)
      return
    }
    fileInputRef.current?.click()
  }

  const uploadFile = async (file: File) => {
    if (isCapped) {
      openPaywall({ featureName: "Knowledge Base Storage" })
      toast.info(`Free plan limit reached (${currentCount}/${maxAssets} documents). Upgrade to Growth Pro to upload up to 25 documents.`)
      return
    }
    setIsUploading(true)
    
    try {
      const formData = new FormData()
      formData.append("file", file)
      
      const res = await fetchWithAuth("/api/assets/knowledge/upload/pdf", {
        method: "POST",
        body: formData
      })
      if (!res.ok) {
        if (res.status === 403) {
          openPaywall({ featureName: "Knowledge Base Storage" })
          toast.info("Free plan document limit reached. Upgrade to Growth Pro for up to 25 documents.")
          return
        }
        throw new Error(await res.text())
      }
      toast.success("Document uploading! Processing in background...")
      mutateAssets()
    } catch (e: any) {
      friendlyToast('Failed to upload document — please try again.', e)
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    uploadFile(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (isUploading) return
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    if (file.type !== "application/pdf" && !file.name.endsWith(".pdf")) {
      toast.error("Please upload a PDF file")
      return
    }
    uploadFile(file)
  }

  return (
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
      aria-label={isCapped ? "Upgrade to Upload Docs" : "Upload a Document"}
      className={cn(
        "relative border border-border/50 bg-card/40 hover:bg-card/70 hover:border-border/80 transition-all rounded-xl p-5 flex flex-col justify-between min-h-[200px] cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring group",
        isDragging && "border-foreground/30 bg-muted/30 ring-1 ring-foreground/10",
        isUploading && "opacity-50 cursor-not-allowed"
      )}
    >
      <div>
        <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 mb-3">
          {isCapped ? <Lock size={15} className="text-amber-500" /> : <UploadCloud size={15} className={isUploading ? 'animate-pulse' : ''} />}
        </div>
        <h3 className="font-medium text-sm text-foreground">
          {isUploading ? "Uploading..." : isCapped ? "Upload Document" : "Upload Document"}
        </h3>
        <p className="text-xs text-muted-foreground mt-1 mb-3 leading-relaxed">
          {isCapped
            ? `Plan limit reached (${currentCount}/${maxAssets} docs)`
            : "Upload pitch decks or case studies so AI can cite real customer ROI in emails."}
        </p>
      </div>

      <button
        type="button"
        tabIndex={-1}
        disabled={isUploading}
        className={cn(
          "w-full py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5 border cursor-pointer",
          isCapped
            ? "border-border/60 bg-muted/40 text-muted-foreground hover:bg-muted/60"
            : "border-border/70 bg-background/60 hover:bg-muted/60 text-foreground"
        )}
      >
        {isUploading ? (
          <span>Uploading...</span>
        ) : isCapped ? (
          <>
            <Lock size={12} className="text-amber-500" />
            <span>Quota Reached</span>
          </>
        ) : (
          <>
            <UploadCloud size={13} className="text-muted-foreground" />
            <span>Choose PDF</span>
          </>
        )}
      </button>

      <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileUpload} />
    </div>
  )
}
