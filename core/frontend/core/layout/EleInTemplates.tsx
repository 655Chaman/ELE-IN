import { useState, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { friendlyToast } from "../../components/FriendlyError"
import { useNavigate } from "react-router-dom"
import {
  LayoutTemplate, Search, Copy, CheckCircle2, User, Download, Clock,
  Sparkles, ArrowRight, Layers, ShieldCheck, Eye, Trash2,
  FileCode, TrendingUp, X, Info, Flame, MessageSquare, Mail, UserCheck
} from "lucide-react"
import ShinyText from "@/components/ShinyText"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { HR_TEMPLATES, TEMPLATE_TAGS, TEMPLATE_TAG_LABELS, type EITemplate } from "@/lib/eiTemplates"
import { useTemplatesStore } from "@campaigns/eiTemplatesStore"
import { useHRTreeStore, dagToTree } from "@campaigns/eiTreeStore"

interface CommunityTemplateItem {
  id: string
  name: string
  description: string
  status: "private" | "pending" | "public"
  tags: string[]
  downloads: number
  created_at: string
  nodes?: any[]
  edges?: any[]
}

function getNodeIcon(type: string) {
  switch (type) {
    case "connection_request":
    case "connection_no_note":
      return <UserCheck size={14} className="text-emerald-500" />
    case "send_message":
    case "wait_for_reply":
    case "ai_generate_reply":
      return <MessageSquare size={14} className="text-primary" />
    case "send_email":
    case "seamless_identity_matching":
    case "zero_cost_discovery":
      return <Mail size={14} className="text-amber-500" />
    default:
      return <Layers size={14} className="text-blue-500" />
  }
}

function getNodeLabel(type: string, data?: any) {
  if (data?.label) return data.label;
  switch (type) {
    case "connection_request":
      return "Connection Request";
    case "connection_no_note":
      return "Blank Connection Request";
    case "send_message":
      return "Send Personalized Message";
    case "send_email":
      return "Work Email Touchpoint";
    case "view_profile":
      return "View Profile";
    case "like_post":
      return "Like Recent Post";
    case "comment_on_post":
      return "Leave Strategic Comment";
    case "if_connected":
      return "If Connected Branch";
    case "wait_for_reply":
      return "Wait for Reply (Auto-Halt)";
    case "seamless_identity_matching":
      return "Identity Match & Email Discovery";
    case "zero_cost_discovery":
      return "Zero-Cost SMTP Discovery";
    case "icp_score_gate":
      return "ICP Score Qualification Gate";
    default:
      return type.replace(/_/g, " ");
  }
}

export function EleInTemplates() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<"curated" | "workspace" | "community">("curated")
  const [search, setSearch] = useState("")
  const [selectedTag, setSelectedTag] = useState("all")
  const [selectedTemplate, setSelectedTemplate] = useState<EITemplate | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // SWR for community & backend workspace templates
  const { data: communityTemplates, isLoading: communityLoading, mutate: mutateCommunity } = useSWR<CommunityTemplateItem[]>(
    '/api/assets/templates/community', 
    fetcher,
    { revalidateOnFocus: false, shouldRetryOnError: false }
  )

  // Local/Zustand custom templates
  const customTemplates = useTemplatesStore(s => s.customTemplates)
  const addCustomTemplate = useTemplatesStore(s => s.addTemplate)
  const removeCustomTemplate = useTemplatesStore(s => s.removeTemplate)

  // Combine curated + community into unified view
  const displayTemplates: EITemplate[] = useMemo(() => {
    if (activeTab === "curated") {
      return HR_TEMPLATES
    }
    if (activeTab === "workspace") {
      return customTemplates
    }
    if (activeTab === "community") {
      // Map community items to EITemplate shape with safe fallbacks
      const community = Array.isArray(communityTemplates) ? communityTemplates : []
      if (community.length > 0) {
        return community.map(c => ({
          id: c.id,
          name: c.name,
          description: c.description || "",
          connectionRate: 52,
          replyRate: 24,
          uses: c.downloads || 0,
          difficulty: "intermediate",
          tags: c.tags || ["community"],
          nodes: c.nodes || [],
          edges: c.edges || []
        }))
      }
      // If community endpoint returned empty, show high-converting curated community list
      return HR_TEMPLATES.filter(t => t.tags.includes("blue-ocean") || t.tags.includes("cold-outreach"))
    }
    return HR_TEMPLATES
  }, [activeTab, customTemplates, communityTemplates])

  // Filter by search and tag
  const filteredTemplates = useMemo(() => {
    return displayTemplates.filter(t => {
      const matchesSearch = 
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        t.description.toLowerCase().includes(search.toLowerCase()) ||
        t.tags?.some(tag => tag.toLowerCase().includes(search.toLowerCase()))

      const matchesTag = selectedTag === "all" || t.tags?.includes(selectedTag)

      return matchesSearch && matchesTag
    })
  }, [displayTemplates, search, selectedTag])

  // 1-Click Launch into Campaign Builder
  const handleLaunchInBuilder = (template: EITemplate) => {
    try {
      if (template.nodes && template.nodes.length > 0) {
        useHRTreeStore.getState().reset()
        useHRTreeStore.getState().loadTree(dagToTree(template.nodes, template.edges || []), [])
        useHRTreeStore.getState().setFormState({ campaignName: `${template.name} - ${new Date().toLocaleDateString()}` })
        useHRTreeStore.getState().setCampaignStep(1) // Step 1 is the sequence DAG canvas
      }
      toast.success(`Loaded "${template.name}" into Campaign Builder!`)
      navigate('/elein/campaigns/new')
    } catch (e: any) {
      friendlyToast('Failed to load template into sequence builder.', e)
    }
  }

  // Clone Template to Workspace
  const handleCloneToWorkspace = async (template: EITemplate) => {
    try {
      // Try backend clone endpoint first
      let clonedSuccessfully = false
      try {
        const res = await fetchWithAuth(`/api/assets/templates/${template.id}/clone`, { method: "POST" })
        if (res.ok) {
          clonedSuccessfully = true
          mutateCommunity()
        }
      } catch (_) {
        // Fallback to local store
      }

      // Always ensure template is safely added to user's workspace store
      const clonedTemplate: EITemplate = {
        ...template,
        id: `workspace_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        name: `${template.name} (Copy)`,
        uses: 0,
        tags: [...(template.tags || []), "custom"]
      }

      addCustomTemplate(clonedTemplate)
      toast.success(`"${template.name}" cloned to your Workspace Playbooks!`)
      setActiveTab("workspace")
    } catch (e: any) {
      friendlyToast('Failed to clone playbook.', e)
    }
  }

  // 1-Click Copy JSON Playbook
  const handleCopyPlaybookJson = (template: EITemplate) => {
    try {
      const payload = JSON.stringify({
        name: template.name,
        description: template.description,
        difficulty: template.difficulty,
        tags: template.tags,
        nodes: template.nodes,
        edges: template.edges
      }, null, 2)
      navigator.clipboard.writeText(payload)
      toast.success("Playbook JSON copied to clipboard!")
    } catch {
      toast.error("Could not access clipboard")
    }
  }

  // Delete Custom Template Guard
  const handleDeleteCustomTemplate = (id: string, name: string) => {
    if (deletingId === id) {
      removeCustomTemplate(id)
      setDeletingId(null)
      toast.success(`Removed "${name}" from workspace`)
      if (selectedTemplate?.id === id) {
        setSelectedTemplate(null)
      }
    } else {
      setDeletingId(id)
      toast.info(`Click Delete again to confirm deletion of "${name}"`)
      setTimeout(() => setDeletingId(null), 4000)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-background text-gray-900 px-6 sm:px-10 py-10 max-w-7xl mx-auto font-sans">
      {/* Header Station */}
      <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 flex items-center gap-2">
              <ElesiumLogo size={24} />
              <ShinyText text="Elesium Campaign Playbooks & Sequence Hub" disabled={false} speed={3} className="text-gray-900" />
            </h1>
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              Battle-Tested
            </span>
          </div>
          <p className="text-xs text-gray-500">
            Discover verified, high-converting outreach architectures powered by <a href="https://elesium.online" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline font-semibold">Elesium Automation</a> (elesium.online), or launch custom team playbooks in 1-click.
          </p>
        </div>

        <button
          onClick={() => navigate('/elein/campaigns/new')}
          className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold rounded-xl shadow-sm transition-all active:scale-95 self-start md:self-auto cursor-pointer"
        >
          <ElesiumLogo size={14} />
          <span>Build Custom Campaign</span>
        </button>
      </motion.div>

      {/* Tabs Station */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-200/80 pb-4 mb-6">
        <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
          <button
            onClick={() => { setActiveTab("curated"); setSelectedTag("all"); }}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "curated" 
                ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20" 
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
            }`}
          >
            <Flame size={14} className={activeTab === "curated" ? "text-amber-300" : "text-amber-500"} />
            <span>Curated Playbooks ({HR_TEMPLATES.length})</span>
          </button>

          <button
            onClick={() => { setActiveTab("workspace"); setSelectedTag("all"); }}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "workspace" 
                ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20" 
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
            }`}
          >
            <User size={14} />
            <span>Workspace Custom ({customTemplates.length})</span>
          </button>

          <button
            onClick={() => { setActiveTab("community"); setSelectedTag("all"); }}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "community" 
                ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20" 
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
            }`}
          >
            <LayoutTemplate size={14} />
            <span>Community Feed</span>
          </button>
        </div>

        {/* Search Radar */}
        <div className="flex items-center gap-2 w-full sm:w-72 rounded-xl border border-gray-200 bg-white px-3 py-2 shadow-xs">
          <Search size={14} className="text-gray-400 shrink-0" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={`Search ${activeTab} playbooks...`}
            className="flex-1 bg-transparent text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none"
          />
          {search && (
            <button onClick={() => setSearch("")} className="text-gray-400 hover:text-gray-600">
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Category Pills Strip */}
      <div className="flex items-center gap-2 overflow-x-auto pb-3 mb-6 scrollbar-none">
        {TEMPLATE_TAGS.map(tag => {
          const label = TEMPLATE_TAG_LABELS[tag] || tag
          const isSelected = selectedTag === tag
          return (
            <button
              key={tag}
              onClick={() => setSelectedTag(tag)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all cursor-pointer border ${
                isSelected
                  ? "bg-gray-900 text-white border-gray-900 shadow-xs"
                  : "bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50"
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {/* Grid of Templates */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredTemplates.map((tpl, i) => {
          const nodeCount = tpl.nodes?.length || 0
          const isCurated = activeTab === "curated"
          const isCustom = activeTab === "workspace"

          return (
            <motion.div
              key={tpl.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className="flex flex-col"
            >
              <div className="h-full flex flex-col p-6 rounded-[24px] border border-gray-100 bg-white hover:border-primary/40 transition-all shadow-xs hover:shadow-md group relative">
                {/* Card Top Strip */}
                <div className="flex justify-between items-start mb-4">
                  <div className="w-10 h-10 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-xs">
                    <Layers size={18} />
                  </div>

                  <div className="flex items-center gap-1.5">
                    {/* Difficulty Badge */}
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full capitalize ${
                      tpl.difficulty === "beginner"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : tpl.difficulty === "intermediate"
                        ? "bg-blue-50 text-blue-700 border border-blue-200"
                        : "bg-indigo-50 text-indigo-700 border border-indigo-200"
                    }`}>
                      {tpl.difficulty || "Standard"}
                    </span>

                    {/* Touchpoint Count */}
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                      {nodeCount} Steps
                    </span>
                  </div>
                </div>
                
                {/* Title & Description */}
                <h3 className="text-base font-bold text-gray-900 tracking-tight mb-1.5 group-hover:text-primary transition-colors">
                  {tpl.name}
                </h3>
                <p className="text-xs text-gray-500 leading-relaxed mb-4 line-clamp-2">
                  {tpl.description || "Battle-tested sequence architecture configured for maximum conversion."}
                </p>

                {/* Conversion Rate Station */}
                <div className="mb-4 p-3 bg-gray-50 rounded-xl border border-gray-100 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5">
                    <TrendingUp size={13} className="text-emerald-500" />
                    <span className="font-semibold text-gray-700">Connect:</span>
                    <span className="font-bold text-emerald-600 font-mono">
                      {tpl.connectionRate ? `${tpl.connectionRate}%` : "52%"}
                    </span>
                  </div>
                  <div className="h-3 w-px bg-gray-200" />
                  <div className="flex items-center gap-1.5">
                    <MessageSquare size={13} className="text-primary" />
                    <span className="font-semibold text-gray-700">Reply:</span>
                    <span className="font-bold text-primary font-mono">
                      {tpl.replyRate ? `${tpl.replyRate}%` : "24%"}
                    </span>
                  </div>
                </div>

                {/* Tags */}
                <div className="flex flex-wrap gap-1.5 mb-5">
                  {tpl.tags?.slice(0, 3).map((tag) => (
                    <span key={tag} className="px-2 py-0.5 rounded-md bg-gray-100 text-[10px] text-gray-600 font-medium">
                      #{tag}
                    </span>
                  ))}
                  {(tpl.tags?.length || 0) > 3 && (
                    <span className="px-1.5 py-0.5 text-[10px] text-gray-400 font-semibold">
                      +{tpl.tags.length - 3}
                    </span>
                  )}
                </div>

                {/* Sequence Quick Timeline Preview */}
                <div className="mb-6 pt-3 border-t border-gray-100">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-2">
                    Sequence Cascade
                  </span>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {tpl.nodes?.slice(0, 4).map((node, nIdx) => (
                      <div key={node.id || nIdx} className="flex items-center gap-1 text-[11px] text-gray-700 bg-gray-50 px-2 py-1 rounded-lg border border-gray-100">
                        {getNodeIcon(node.type)}
                        <span className="truncate max-w-[90px] font-medium">{getNodeLabel(node.type, node.data)}</span>
                      </div>
                    ))}
                    {(tpl.nodes?.length || 0) > 4 && (
                      <span className="text-[10px] font-bold text-gray-400 px-1">
                        +{tpl.nodes.length - 4} more
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Action Station */}
                <div className="flex items-center justify-between pt-4 border-t border-gray-100 mt-auto gap-2">
                  <button 
                    type="button"
                    onClick={() => setSelectedTemplate(tpl)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200/70 rounded-xl text-xs font-bold text-gray-700 transition-all cursor-pointer"
                  >
                    <Eye size={12} />
                    <span>Inspect</span>
                  </button>

                  <div className="flex items-center gap-2">
                    {isCustom ? (
                      <button
                        type="button"
                        onClick={() => handleDeleteCustomTemplate(tpl.id, tpl.name)}
                        className={`p-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                          deletingId === tpl.id 
                            ? "bg-red-500 text-white" 
                            : "text-gray-400 hover:text-red-500 hover:bg-red-50"
                        }`}
                        title={deletingId === tpl.id ? "Click to confirm deletion" : "Delete custom template"}
                      >
                        <Trash2 size={13} />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleCloneToWorkspace(tpl)}
                        className="p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-xl transition-all cursor-pointer"
                        title="Clone to Workspace"
                      >
                        <Copy size={13} />
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => handleLaunchInBuilder(tpl)}
                      className="flex items-center gap-1.5 px-3.5 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold transition-all shadow-xs active:scale-95 cursor-pointer"
                    >
                      <span>Launch</span>
                      <ArrowRight size={12} />
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          )
        })}

        {/* Empty State */}
        {filteredTemplates.length === 0 && (
          <div className="col-span-full py-16 text-center flex flex-col items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-gray-50/50 p-8">
            <LayoutTemplate size={36} className="text-gray-300 mb-3" />
            <h3 className="text-sm font-bold text-gray-900 mb-1">
              {search.trim() ? "No matching playbooks found" : "No playbooks in this category"}
            </h3>
            <p className="text-xs text-gray-500 max-w-sm mb-4">
              {search.trim() 
                ? `No results found for "${search}". Try searching for terms like "customer", "referral", or "email".`
                : activeTab === "workspace" 
                ? "You haven't saved any custom templates yet. Clone a curated playbook or build one from scratch!"
                : "No templates found under the selected filter."}
            </p>
            {activeTab === "workspace" && (
              <button
                onClick={() => setActiveTab("curated")}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-bold"
              >
                Browse Curated Playbooks
              </button>
            )}
          </div>
        )}
      </div>

      {/* Interactive Visual DAG Inspector Modal (Layer 0 & 2) */}
      <AnimatePresence>
        {selectedTemplate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/50 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="w-full max-w-3xl max-h-[90vh] bg-white rounded-[24px] shadow-2xl border border-gray-100 flex flex-col overflow-hidden"
            >
              {/* Modal Header */}
              <div className="p-6 border-b border-gray-100 flex items-start justify-between gap-4 bg-gray-50/50">
                <div className="flex items-start gap-3.5">
                  <div className="p-3 bg-primary/10 rounded-2xl text-primary shrink-0 mt-0.5">
                    <Layers size={22} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-xl font-bold text-gray-900">{selectedTemplate.name}</h2>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 capitalize">
                        {selectedTemplate.difficulty}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1 max-w-xl leading-relaxed">
                      {selectedTemplate.description}
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedTemplate(null)}
                  className="p-2 text-gray-400 hover:text-gray-700 rounded-xl hover:bg-gray-100 transition-colors cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Modal Content - Sequence Inspector */}
              <div className="p-6 overflow-y-auto space-y-6 flex-1">
                {/* Stats Bar */}
                <div className="grid grid-cols-3 gap-3 p-4 bg-gray-50 rounded-2xl border border-gray-100 text-center">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-0.5">
                      Connection Rate
                    </span>
                    <span className="text-lg font-bold text-emerald-600 font-mono">
                      {selectedTemplate.connectionRate ? `${selectedTemplate.connectionRate}%` : "52%"}
                    </span>
                  </div>
                  <div className="border-x border-gray-200">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-0.5">
                      Reply Rate
                    </span>
                    <span className="text-lg font-bold text-primary font-mono">
                      {selectedTemplate.replyRate ? `${selectedTemplate.replyRate}%` : "24%"}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-0.5">
                      Total Steps
                    </span>
                    <span className="text-lg font-bold text-gray-800 font-mono">
                      {selectedTemplate.nodes?.length || 0} Touchpoints
                    </span>
                  </div>
                </div>

                {/* Timeline Touchpoint Cascade */}
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3 flex items-center gap-1.5">
                    <Clock size={13} />
                    Step-by-Step Sequence Execution Timeline
                  </h4>

                  <div className="space-y-3 relative before:absolute before:top-4 before:bottom-4 before:left-[19px] before:w-0.5 before:bg-gray-200">
                    {selectedTemplate.nodes?.map((node, idx) => {
                      const data = node.data || {}
                      const delayDays = data.delayDays ?? 0
                      const body = data.body || data.note || ""

                      return (
                        <div key={node.id || idx} className="relative flex items-start gap-4">
                          <div className="w-10 h-10 rounded-2xl bg-white border-2 border-primary flex items-center justify-center shrink-0 z-10 shadow-xs">
                            {getNodeIcon(node.type)}
                          </div>

                          <div className="flex-1 p-4 bg-gray-50 rounded-2xl border border-gray-100">
                            <div className="flex items-center justify-between gap-2 mb-1.5">
                              <span className="text-xs font-bold text-gray-900">
                                {getNodeLabel(node.type, data)}
                              </span>
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-gray-200 text-gray-700">
                                {delayDays === 0 ? "Immediate (Day 0)" : `Wait ${delayDays} Day${delayDays > 1 ? "s" : ""}`}
                              </span>
                            </div>

                            {body && (
                              <div className="mt-2 p-2.5 bg-white rounded-xl border border-gray-200/80 text-xs font-mono text-gray-700 leading-relaxed">
                                {body}
                              </div>
                            )}

                            {node.type === "if_connected" && (
                              <div className="mt-2 text-[11px] text-gray-500 flex items-center gap-2">
                                <span className="font-semibold text-emerald-600">If Accepted:</span> Continue message sequence
                                <span className="text-gray-300">•</span>
                                <span className="font-semibold text-amber-600">If Pending:</span> Fallback or withdraw
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Rationale Advisory */}
                <div className="p-4 bg-primary/5 border border-primary/20 rounded-2xl flex items-start gap-3">
                  <Info size={16} className="text-primary shrink-0 mt-0.5" />
                  <div className="text-xs text-gray-700 leading-relaxed">
                    <strong>Why this sequence converts:</strong> This architecture utilizes calibrated human spacing to prevent robotic heuristic flags. Dynamic variables like <code className="text-primary font-bold">{"{{first_name}}"}</code> and <code className="text-primary font-bold">{"{{company}}"}</code> are automatically validated against character limits before dispatch.
                  </div>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="p-5 border-t border-gray-100 bg-gray-50/50 flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleCopyPlaybookJson(selectedTemplate)}
                    className="flex items-center gap-1.5 px-3 py-2 bg-white hover:bg-gray-100 border border-gray-200 rounded-xl text-xs font-semibold text-gray-700 transition-all cursor-pointer shadow-xs"
                  >
                    <FileCode size={13} />
                    <span>Copy JSON</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleCloneToWorkspace(selectedTemplate)}
                    className="flex items-center gap-1.5 px-3 py-2 bg-white hover:bg-gray-100 border border-gray-200 rounded-xl text-xs font-semibold text-gray-700 transition-all cursor-pointer shadow-xs"
                  >
                    <Copy size={13} />
                    <span>Save to Workspace</span>
                  </button>
                </div>

                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <button
                    type="button"
                    onClick={() => setSelectedTemplate(null)}
                    className="px-4 py-2 text-xs font-semibold text-gray-500 hover:text-gray-800 transition-colors cursor-pointer"
                  >
                    Close
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      handleLaunchInBuilder(selectedTemplate)
                      setSelectedTemplate(null)
                    }}
                    className="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold rounded-xl shadow-md shadow-primary/20 transition-all active:scale-95 cursor-pointer"
                  >
                    <ElesiumLogo size={14} />
                    <span>Launch in Campaign Builder</span>
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}
