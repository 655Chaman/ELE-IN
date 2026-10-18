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
        "relative border border-border/60 bg-muted/20 hover:bg-muted/30 hover:border-primary/50 transition-all rounded-xl p-5 flex flex-col justify-between cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group",
        isDragging && "border-primary bg-primary/5 ring-2 ring-primary/20",
        isUploading && "opacity-50 cursor-not-allowed"
      )}
    >
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); toast.info("Upload a PDF document or pitch deck about your company. Good examples: your sales pitch, capabilities one-pager, case studies, or product overview."); }}
        className="absolute top-4 right-4 w-6 h-6 rounded-full bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground flex items-center justify-center transition-colors z-10"
        title="What should I upload?"
        aria-label="What should I upload?"
      >
        <Info size={13} />
      </button>

      <div>
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary mb-2">
          {isCapped ? <Lock size={18} className="text-amber-600 dark:text-amber-400" /> : <UploadCloud size={18} className={isUploading ? 'animate-pulse' : ''} />}
        </div>
        <h3 className="font-semibold text-sm text-foreground">
          {isUploading ? "Uploading..." : isCapped ? "Upgrade to Upload Docs" : "Upload a Document"}
        </h3>
        <p className="text-xs text-muted-foreground mt-1 mb-3">
          {isCapped
            ? `Limit reached (${currentCount}/${maxAssets} docs)`
            : "Sales deck, pitch doc, PDF up to 10MB"}
        </p>
      </div>

      <button
        type="button"
        tabIndex={-1}
        disabled={isUploading}
        className={cn(
          "w-full py-2 rounded-lg text-xs font-semibold transition-all flex items-center justify-center gap-1.5 shadow-xs cursor-pointer",
          isCapped
            ? "bg-muted text-foreground border border-border hover:bg-muted/80"
            : "bg-primary text-primary-foreground hover:bg-primary/90"
        )}
      >
        {isUploading ? (
          <span>Uploading...</span>
        ) : isCapped ? (
          <>
            <Lock size={12} className="text-amber-600 dark:text-amber-400" />
            <span>Unlock More Docs</span>
          </>
        ) : (
          <>
            <UploadCloud size={12} />
            <span>Choose PDF</span>
          </>
        )}
      </button>

      <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileUpload} />
    </div>
  )
}
