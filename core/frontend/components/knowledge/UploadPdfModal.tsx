import { UploadCloud } from "lucide-react"
import { toast } from "sonner"
import { friendlyToast } from "../FriendlyError"
import { useRef, useState } from "react"
import { fetchWithAuth } from "@/lib/apiClient"

export function UploadPdfModal({ mutateAssets }: { mutateAssets: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      
      const res = await fetchWithAuth("/api/assets/knowledge/upload/pdf", {
        method: "POST",
        body: formData
      });
      if (!res.ok) throw new Error(await res.text());
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
      onClick={() => !isUploading && fileInputRef.current?.click()}
      className={`relative border border-dashed border-slate-300 dark:border-border/60 bg-slate-50 dark:bg-muted/10 hover:bg-blue-50/60 dark:hover:bg-blue-500/5 hover:border-blue-400 dark:hover:border-blue-500/50 transition-all rounded-3xl p-6 flex flex-col items-center justify-center text-center group ${isUploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <button
        onClick={(e) => { e.stopPropagation(); toast.info("Upload a PDF, slide deck, or Word doc about your company. Good examples: your sales pitch, a one-pager, a capabilities doc, customer case studies, or your product spec sheet."); }}
        className="absolute top-3 right-3 w-6 h-6 rounded-full bg-slate-200 dark:bg-muted text-muted-foreground hover:bg-blue-100 dark:hover:bg-blue-900/50 hover:text-blue-600 dark:hover:text-blue-400 flex items-center justify-center text-xs font-bold transition-colors z-10"
        title="What should I upload?"
      >
        i
      </button>
      <UploadCloud size={24} className={`text-blue-600 dark:text-blue-500 mb-3 group-hover:scale-110 transition-transform ${isUploading ? 'animate-bounce' : ''}`} />
      <h3 className="font-semibold text-sm text-foreground">{isUploading ? "Uploading..." : "Upload a Document"}</h3>
      <p className="text-xs text-muted-foreground mt-1">Sales deck, pitch doc, PDF<br /><span className="text-blue-500 font-medium">up to 10MB</span></p>
      <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx" className="hidden" onChange={handleFileUpload} />
    </div>
  )
}
