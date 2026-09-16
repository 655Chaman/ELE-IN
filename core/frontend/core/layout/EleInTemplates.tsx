import { useState } from "react"
import { motion } from "motion/react"
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import {
  LayoutTemplate, Search, Copy, CheckCircle2, User, Download, Clock
} from "lucide-react"
import SpotlightCard from "@/components/SpotlightCard"
import ShinyText from "@/components/ShinyText"

interface Template {
  id: string
  name: string
  description: string
  status: "private" | "pending" | "public"
  tags: string[]
  downloads: number
  created_at: string
}

export function EleInTemplates() {
  const [activeTab, setActiveTab] = useState<"community" | "mine">("community")
  const [search, setSearch] = useState("")

  const { data: communityTemplates, mutate: mutateCommunity } = useSWR<Template[]>('/api/assets/templates/community', fetcher)
  const { data: myTemplates, mutate: mutateMine } = useSWR<Template[]>('/api/assets/templates/mine', fetcher)

  const handleClone = async (id: string) => {
    try {
      const res = await fetchWithAuth(`/api/assets/templates/${id}/clone`, { method: "POST" })
      if (!res.ok) throw new Error("Failed to clone template")
      toast.success("Template cloned to your workspace!")
      mutateMine()
      mutateCommunity()
    } catch (e: any) {
      toast.error(e.message || "Failed to clone template")
    }
  }

  const safeCommunity = Array.isArray(communityTemplates) ? communityTemplates : []
  const safeMine = Array.isArray(myTemplates) ? myTemplates : []

  const displayTemplates = activeTab === "community" ? safeCommunity : safeMine
  const filtered = displayTemplates.filter(t => t.name.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-8 py-10 max-w-6xl mx-auto font-sans">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold mb-1">
            <ShinyText text="Template Hub" disabled={false} speed={3} className="" />
          </h1>
          <p className="text-xs text-muted-foreground">Discover high-performing community sequences or manage your own custom templates.</p>
        </div>
      </motion.div>

      {/* TABS */}
      <div className="flex items-center gap-3 border-b border-border/50 pb-4 mb-6">
        <button
          onClick={() => setActiveTab("community")}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
            activeTab === "community" ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/50"
          }`}
        >
          <LayoutTemplate size={14} /> Community Feed
        </button>
        <button
          onClick={() => setActiveTab("mine")}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
            activeTab === "mine" ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/50"
          }`}
        >
          <User size={14} /> My Workspace
        </button>
      </div>

      <div className="flex items-center gap-2 mb-6 max-w-md rounded-lg border border-border/50 bg-background/50 backdrop-blur-md px-3 py-2.5 shadow-sm">
        <Search size={14} className="text-muted-foreground shrink-0" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={`Search ${activeTab} templates...`}
          className="flex-1 bg-transparent text-xs text-foreground placeholder-muted-foreground focus:outline-none"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {filtered.map((tpl, i) => (
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
                {activeTab === "mine" && tpl.status === "pending" && (
                  <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-500/10 text-amber-500 text-[10px] font-bold">
                    <Clock size={12} /> Under Review
                  </span>
                )}
                {activeTab === "mine" && tpl.status === "public" && (
                  <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-500 text-[10px] font-bold">
                    <CheckCircle2 size={12} /> Published
                  </span>
                )}
              </div>
              
              <h3 className="text-base font-bold text-foreground tracking-tight mb-2">
                {tpl.name}
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6 flex-1 line-clamp-3">
                {tpl.description || "No description provided."}
              </p>

              <div className="flex flex-wrap gap-2 mb-6">
                {tpl.tags?.map((tag) => (
                  <span key={tag} className="px-2 py-1 rounded-md bg-background border border-border/50 text-[10px] text-muted-foreground font-medium">
                    {tag}
                  </span>
                ))}
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-border/50 mt-auto">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
                  <Download size={14} className="text-primary" />
                  {tpl.downloads} clones
                </div>
                {activeTab === "community" ? (
                  <button 
                    onClick={() => handleClone(tpl.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-background hover:bg-muted border border-border/50 rounded-lg text-xs font-bold text-foreground transition-all shadow-sm"
                  >
                    <Copy size={12} /> Clone
                  </button>
                ) : (
                  <button className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary rounded-lg text-xs font-bold transition-all">
                    Use Template
                  </button>
                )}
              </div>
            </SpotlightCard>
          </motion.div>
        ))}
        {filtered.length === 0 && (
          <div className="col-span-full py-20 text-center flex flex-col items-center">
            <LayoutTemplate size={32} className="text-muted-foreground/30 mb-4" />
            <h3 className="text-sm font-bold text-foreground mb-1">No templates found</h3>
            <p className="text-xs text-muted-foreground">Try adjusting your search criteria.</p>
          </div>
        )}
      </div>
    </div>
  )
}
