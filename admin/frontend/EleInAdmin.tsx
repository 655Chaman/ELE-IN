import { useState } from "react"
import { motion } from "motion/react"
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { LayoutTemplate, CheckCircle, XCircle, Clock, Key, Plus, Trash2, RefreshCw, AlertCircle } from "lucide-react"
import SpotlightCard from "@/components/SpotlightCard"
import ShinyText from "@/components/ShinyText"

interface Template {
  id: string
  name: string
  description: string
  status: "private" | "pending" | "public" | "rejected"
  tags: string[]
  downloads: number
  created_at: string
}

interface ApiKey {
  id: string
  provider: string
  api_key: string
  status: string
  error_count: number
  last_used_at: string
}

export function EleInAdmin() {
  const [activeTab, setActiveTab] = useState<"templates" | "keys">("templates")
  
  // Template State
  const { data: pendingTemplates, mutate: mutateTemplates } = useSWR<Template[]>('/api/assets/templates/admin/pending', fetcher)
  const [loadingId, setLoadingId] = useState<string | null>(null)

  // API Key State
  const { data: apiKeys, mutate: mutateKeys } = useSWR<ApiKey[]>('/api/settings/admin/api-keys', fetcher)
  const [newKey, setNewKey] = useState("")
  const [isAddingKey, setIsAddingKey] = useState(false)

  const handleAction = async (id: string, action: "approve" | "reject") => {
    setLoadingId(id)
    try {
      const res = await fetchWithAuth(`/api/assets/templates/admin/${id}/${action}`, { method: "POST" })
      if (!res.ok) throw new Error(`Failed to ${action} template. Check if you have the SUPABASE_SERVICE_KEY configured.`)
      toast.success(`Template ${action}d successfully!`)
      mutateTemplates()
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setLoadingId(null)
    }
  }

  const handleAddKey = async () => {
    if (!newKey.trim().startsWith("nvapi-")) {
      toast.error("Invalid key format. Must start with nvapi-")
      return
    }
    setIsAddingKey(true)
    try {
      const res = await fetchWithAuth("/api/settings/admin/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: newKey.trim() })
      })
      if (!res.ok) {
        let err = "Failed to add key"
        try { const d = await res.json(); err = d.detail || err; } catch(e) {}
        throw new Error(err)
      }
      toast.success("NVIDIA API key added to pool!")
      setNewKey("")
      mutateKeys()
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setIsAddingKey(false)
    }
  }

  const handleDeleteKey = async (id: string) => {
    try {
      await fetchWithAuth(`/api/settings/admin/api-keys/${id}`, { method: "DELETE" })
      toast.success("Key removed from pool")
      mutateKeys()
    } catch (e: any) {
      toast.error("Failed to delete key")
    }
  }

  const handleResetKey = async (id: string) => {
    try {
      await fetchWithAuth(`/api/settings/admin/api-keys/${id}/reset`, { method: "PUT" })
      toast.success("Key status reset to active")
      mutateKeys()
    } catch (e: any) {
      toast.error("Failed to reset key")
    }
  }

  const safeTemplates = Array.isArray(pendingTemplates) ? pendingTemplates : []
  const safeKeys = Array.isArray(apiKeys) ? apiKeys : []

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-8 py-10 max-w-6xl mx-auto font-sans">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <h1 className="text-2xl font-bold mb-1">
          <ShinyText text="System Admin" disabled={false} speed={3} className="" />
        </h1>
        <p className="text-xs text-muted-foreground">Platform-level controls for community curation and AI capacity.</p>
        
        <div className="flex items-center gap-4 mt-6 border-b border-border/50 pb-2">
          <button 
            onClick={() => setActiveTab("templates")}
            className={`text-sm font-semibold pb-2 transition-all ${activeTab === "templates" ? "text-foreground border-b-2 border-primary" : "text-muted-foreground hover:text-foreground"}`}
          >
            Template Curation
          </button>
          <button 
            onClick={() => setActiveTab("keys")}
            className={`text-sm font-semibold pb-2 transition-all ${activeTab === "keys" ? "text-foreground border-b-2 border-primary" : "text-muted-foreground hover:text-foreground"}`}
          >
            AI Key Pool
          </button>
        </div>
      </motion.div>

      {activeTab === "templates" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {safeTemplates.map((tpl, i) => (
            <motion.div
              key={tpl.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <SpotlightCard className="h-full flex flex-col p-6 rounded-2xl border border-border/50 bg-muted/10 backdrop-blur-md hover:border-border transition-all">
                <div className="flex justify-between items-start mb-4">
                  <div className="w-10 h-10 rounded-xl bg-background border border-border/50 flex items-center justify-center">
                    <LayoutTemplate size={18} className="text-primary" />
                  </div>
                  <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-warning/10 text-warning text-[10px] font-bold">
                    <Clock size={12} /> Pending Review
                  </span>
                </div>
                
                <h3 className="text-base font-bold text-foreground tracking-tight mb-2">
                  {tpl.name}
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed mb-6 flex-1 line-clamp-3">
                  {tpl.description || "No description provided."}
                </p>

                <div className="flex items-center gap-2 pt-4 border-t border-border/50 mt-auto">
                  <button 
                    onClick={() => handleAction(tpl.id, "approve")}
                    disabled={loadingId === tpl.id}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-success/10 hover:bg-success/20 border border-success/20 text-success rounded-lg text-xs font-bold transition-all disabled:opacity-50"
                  >
                    <CheckCircle size={14} /> Approve
                  </button>
                  <button 
                    onClick={() => handleAction(tpl.id, "reject")}
                    disabled={loadingId === tpl.id}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-destructive/10 hover:bg-destructive/20 border border-destructive/20 text-destructive rounded-lg text-xs font-bold transition-all disabled:opacity-50"
                  >
                    <XCircle size={14} /> Reject
                  </button>
                </div>
              </SpotlightCard>
            </motion.div>
          ))}
          {safeTemplates.length === 0 && (
            <div className="col-span-full py-20 text-center flex flex-col items-center">
              <CheckCircle size={32} className="text-success/50 mb-4" />
              <h3 className="text-sm font-bold text-foreground mb-1">Queue Empty</h3>
              <p className="text-xs text-muted-foreground">All pending templates have been reviewed.</p>
            </div>
          )}
        </div>
      )}

      {activeTab === "keys" && (
        <div className="space-y-6">
          <SpotlightCard className="p-6 rounded-2xl border border-border/50 bg-muted/10 backdrop-blur-md">
            <h3 className="text-sm font-bold mb-4 flex items-center gap-2"><Key size={16} className="text-primary" /> Add NVIDIA API Key</h3>
            <div className="flex gap-3">
              <input 
                type="password"
                placeholder="nvapi-..."
                value={newKey}
                onChange={e => setNewKey(e.target.value)}
                className="flex-1 bg-background border border-border/50 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-primary/50"
              />
              <button 
                onClick={handleAddKey}
                disabled={isAddingKey || !newKey}
                className="flex items-center gap-2 px-5 py-2 bg-foreground text-background font-bold text-sm rounded-xl hover:bg-foreground/90 disabled:opacity-50 transition-all"
              >
                <Plus size={16} /> Add to Pool
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground mt-3">
              Keys are pooled. If one hits a rate limit, the system instantly fails over to the next key automatically.
            </p>
          </SpotlightCard>

          <div className="space-y-3">
            <h3 className="text-sm font-bold mb-2">Active Pool ({safeKeys.length})</h3>
            {safeKeys.map(k => (
              <div key={k.id} className="flex items-center justify-between p-4 rounded-xl border border-border/50 bg-background group">
                <div className="flex items-center gap-4">
                  <div className={`w-2 h-2 rounded-full ${k.status === 'active' ? 'bg-success shadow-[0_0_8px_var(--success),0.5)]' : k.status === 'rate_limited' ? 'bg-warning' : 'bg-destructive'}`} />
                  <div>
                    <p className="text-sm font-mono font-medium">{k.api_key}</p>
                    <p className="text-xs text-muted-foreground capitalize mt-0.5">
                      {k.status.replace("_", " ")} • {k.error_count} errors
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  {k.status !== 'active' && (
                    <button 
                      onClick={() => handleResetKey(k.id)}
                      className="p-2 text-muted-foreground hover:text-success rounded-lg hover:bg-success/10 transition-colors"
                      title="Reset Status"
                    >
                      <RefreshCw size={14} />
                    </button>
                  )}
                  <button 
                    onClick={() => handleDeleteKey(k.id)}
                    className="p-2 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10 transition-colors"
                    title="Remove from pool"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
            {safeKeys.length === 0 && (
              <div className="py-10 text-center flex flex-col items-center bg-background rounded-xl border border-border/50 border-dashed">
                <AlertCircle size={24} className="text-muted-foreground/50 mb-3" />
                <h3 className="text-sm font-bold text-muted-foreground mb-1">Pool is empty</h3>
                <p className="text-xs text-muted-foreground/70">Add a key above to power AI operations.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
