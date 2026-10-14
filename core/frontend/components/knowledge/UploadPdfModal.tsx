import { UploadCloud, Lock } from "lucide-react"
import { toast } from "sonner"
import { friendlyToast } from "../FriendlyError"
import { useRef, useState } from "react"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import useSWR from "swr"

export function UploadPdfModal({ mutateAssets }: { mutateAssets: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)
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

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (isCapped) {
      openPaywall({ featureName: "Knowledge Base Storage" });
      toast.info(`Free plan limit reached (${currentCount}/${maxAssets} documents). Upgrade to Growth Pro to upload up to 25 documents.`);
      return;
    }
    setIsUploading(true);
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      
      const res = await fetchWithAuth("/api/assets/knowledge/upload/pdf", {
        method: "POST",
        body: formData
      });
      if (!res.ok) {
        if (res.status === 403) {
          openPaywall({ featureName: "Knowledge Base Storage" });
          toast.info("Free plan document limit reached. Upgrade to Growth Pro for up to 25 documents.");
          return;
        }
        throw new Error(await res.text());
      }
      toast.success("Document uploading! Processing in background...");
      mutateAssets();
    } catch (e: any) {
      friendlyToast('Failed to upload document — please try again.', e);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div
      onClick={handleZoneClick}
      className={`relative border border-dashed border-slate-300 dark:border-border/60 bg-slate-50 dark:bg-muted/10 hover:bg-blue-50/60 dark:hover:bg-blue-500/5 hover:border-blue-400 dark:hover:border-blue-500/50 transition-all rounded-3xl p-6 flex flex-col items-center justify-center text-center group ${isUploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <button
        onClick={(e) => { e.stopPropagation(); toast.info("Upload a PDF document or pitch deck about your company. Good examples: your sales pitch, capabilities one-pager, case studies, or product overview."); }}
        className="absolute top-3 right-3 w-6 h-6 rounded-full bg-slate-200 dark:bg-muted text-muted-foreground hover:bg-blue-100 dark:hover:bg-blue-900/50 hover:text-blue-600 dark:hover:text-blue-400 flex items-center justify-center text-xs font-bold transition-colors z-10"
        title="What should I upload?"
      >
        i
      </button>
      {isCapped ? (
        <Lock size={24} className="text-amber-500 mb-3" />
      ) : (
        <UploadCloud size={24} className={`text-blue-600 dark:text-blue-500 mb-3 group-hover:scale-110 transition-transform ${isUploading ? 'animate-bounce' : ''}`} />
      )}
      <h3 className="font-semibold text-sm text-foreground">{isUploading ? "Uploading..." : isCapped ? "Upgrade to Upload Docs" : "Upload a Document"}</h3>
      <p className="text-xs text-muted-foreground mt-1">
        {isCapped
          ? `Free limit reached (${currentCount}/${maxAssets} docs). Unlock up to 25.`
          : <>Sales deck, pitch doc, PDF<br /><span className="text-muted-foreground font-medium">up to 10MB (PDF)</span></>}
      </p>
      <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileUpload} />
    </div>
  )
}
