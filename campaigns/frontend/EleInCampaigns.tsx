import { useHRTreeStore } from "@campaigns/eiTreeStore";
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { useState, useEffect, useRef } from "react"
import { cn } from "@/lib/utils"
import { motion, AnimatePresence } from "motion/react"
import { Link, useNavigate } from "react-router-dom"
import { Megaphone, Plus, Search, Play, Pause,
  Trash2, ChevronRight, BarChart2, Users,
  CheckCircle2, Clock, Activity, MoreVertical, Settings
, Briefcase, Link as LinkIcon, Info, Zap } from "lucide-react"

import ShinyText from "@/components/ShinyText"
import StarBorder from "@/components/StarBorder"


const STATUS_CONFIG: Record<string, any> = {
  ACTIVE: { label: "Active", dot: "bg-success", text: "text-success" },
  PAUSED: { label: "Paused", dot: "bg-warning", text: "text-warning" },
  DRAFT: { label: "Draft", dot: "bg-zinc-500", text: "text-zinc-400" },
}

export interface Campaign {
  id: string
  name: string
  description?: string
  status: "ACTIVE" | "PAUSED" | "DRAFT" | string
  sent?: number
  accepted?: number
  replies?: number
  leads_total?: number
  leads_running?: number
  senders?: any[]
  leads_pending?: number
  created_at?: string
  leads_completed?: number
  conversion_rate?: number
}


function EmptyCampaignCard({ id, icon: Icon, title, desc, onSelect }: any) {
  const [showInfo, setShowInfo] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setShowInfo(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  return (
    <motion.div 
      whileHover={{ y: -4 }}
      className="p-8 border border-border/50 bg-card/30 rounded-2xl cursor-pointer hover:border-foreground/30 hover:bg-card/50 hover:shadow-sm transition-all flex flex-col items-center justify-center text-center group relative h-full" 
      onClick={() => onSelect(id)}
    >
      <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
        <Icon size={24} className="text-primary" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">{title}</h3>
      <p className="text-[13px] text-muted-foreground leading-relaxed">{desc}</p>
      
      <div 
        ref={ref}
        className="absolute top-4 right-4 text-muted-foreground hover:text-foreground transition-colors p-1"
        onClick={(e) => {
          e.stopPropagation();
          setShowInfo(!showInfo);
        }}
      >
        <Info size={16} />
        <AnimatePresence>
          {showInfo && (
            <motion.div 
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 top-full mt-2 w-48 p-2 bg-card border border-border rounded-[8px] shadow-xl z-50 text-left pointer-events-auto text-[12px]"
              onClick={(e) => e.stopPropagation()}
            >
              {desc}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

export function EleInCampaigns() {
  const [search, setSearch] = useState("")
  const [draftExists, setDraftExists] = useState(false)
  const [draftTime, setDraftTime] = useState("")
  const [statusTooltipOpen, setStatusTooltipOpen] = useState(false)
  
  // Custom Confirmation Modal State
  const [confirmModal, setConfirmModal] = useState<{isOpen: boolean, title: string, message: string, onConfirm: () => void} | null>(null)

  useEffect(() => {
    const draftStr = localStorage.getItem("elein_unsaved_draft")
    if (draftStr) {
      try {
        const draft = JSON.parse(draftStr)
        if (draft.nodes && draft.nodes.length > 0) {
          setDraftExists(true)
          setDraftTime(new Date(draft.timestamp).toLocaleString())
        }
      } catch(e){
        console.error('Draft parse error:', e)
        toast.error('Failed to parse campaign draft from local storage.')
      }
    }
  }, [])
  
  const navigate = useNavigate()
  const resetTree = useHRTreeStore(state => state.reset)

  const { data: dashboardData, mutate } = useSWR("/api/elein/dashboard/stats", fetcher)
  const campaigns: Campaign[] = dashboardData?.recent_campaigns || dashboardData?.campaigns || []
  
  const { data: workerStatus } = useSWR('/api/elein/worker/status', fetcher, { refreshInterval: 30000 })
  
  const toggleStatus = async (id: string) => {
    const campaign = campaigns.find(c => c.id === id);
    if (!campaign) return;
    const action = campaign.status === 'ACTIVE' ? 'pause' : 'activate';
    try {
      await fetchWithAuth(`/api/elein/campaigns/${id}/${action}`, { method: 'PATCH' });
      toast.success(action === 'activate' ? `Campaign "${campaign.name}" activated` : `Campaign "${campaign.name}" paused`);
      mutate();
    } catch (e: any) {
      toast.error(e.message);
    }
  }
  
  const remove = async (id: string) => {
    const campaign = campaigns.find(c => c.id === id);
    setConfirmModal({
      isOpen: true,
      title: "Delete Campaign",
      message: `Are you sure you want to delete the campaign "${campaign?.name || 'Unknown'}"? This cannot be undone.`,
      onConfirm: async () => {
        setConfirmModal(null);

        try {
          await fetchWithAuth(`/api/elein/campaigns/${id}`, { method: 'DELETE' });
          toast.success(`Campaign "${campaign?.name || 'Unknown'}" deleted`);
          mutate();
        } catch (e: any) {
          toast.error(e.message);
        }
        
      }
    });
  }

  const filtered = campaigns.filter(c =>
     (c.name || "").toLowerCase().includes(search.toLowerCase()) ||
    (c.description || "").toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="max-w-[1200px] mx-auto p-8">
      {/* ─── HEADER ────────────────────────────────────────────────────────────── */}
      <div className="mb-10 flex justify-between items-end">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              <ShinyText text="Campaigns" speed={3} className="text-foreground" />
            </h1>
            {(() => {
              if (!workerStatus) return null;
              
              if (workerStatus.status === "unknown") {
                return (
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold border border-foreground/10 bg-muted/30">
                    <span className="text-muted-foreground">
                      Get Started — connect a LinkedIn account
                    </span>
                  </div>
                );
              }
              
              if (campaigns.length === 0) return null;
              return (
<div className="relative group">
                  <button 
                    onClick={() => setStatusTooltipOpen(!statusTooltipOpen)}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-bold border cursor-pointer hover:bg-muted/30 transition-colors"
                  >
                    <div className={`w-2 h-2 rounded-full ${workerStatus.stalled ? 'bg-destructive animate-pulse' : 'bg-success'}`} />
                    <span className={workerStatus.stalled ? 'text-destructive' : 'text-success'}>
                      {workerStatus.stalled ? 'Engine Stalled' : 'Engine Live'}
                    </span>
                  </button>
                  <div className={cn(
                    "absolute left-1/2 -translate-x-1/2 top-full mt-2 w-max max-w-xs p-2 bg-popover border border-border shadow-xl rounded-lg text-xs text-popover-foreground pointer-events-none transition-opacity z-50",
                    statusTooltipOpen ? "opacity-100 pointer-events-auto" : "opacity-0 group-hover:opacity-100 group-hover:pointer-events-auto"
                  )}>
                    {workerStatus.message}
                    {workerStatus.stalled && <div className="mt-1 font-semibold text-destructive">Please contact support if this persists.</div>}
                  </div>
                </div>
              );
            })()}
          </div>
          <p className="text-sm text-muted-foreground">
            Build and run LinkedIn outreach sequences with multi-account sender rotation.
          </p>
        </div>
        <div className="flex items-center gap-3">
            {campaigns.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-2 bg-muted/30 border border-border/50 rounded-[18px]">
                <Search size={14} className="text-muted-foreground" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search campaigns…"
                  className="flex-1 bg-transparent text-xs text-foreground placeholder-muted-foreground focus:outline-none w-40"
                />
              </div>
            )}
            {campaigns.length > 0 && (
              <button
                onClick={() => { resetTree(); navigate('/elein/campaigns/new'); }}
                className="flex items-center gap-2 bg-success hover:bg-success/90 text-success-foreground px-4 py-2.5 rounded-2xl font-bold transition-all shadow-md active:scale-95"
              >
                <Zap size={16} className="fill-current text-success-foreground" /> Start outreach
              </button>
            )}
          </div>
      </div>

      {/* ─── CAMPAIGNS LIST ─────────────────────────────────────────────────────── */}
      <>
        {draftExists && (
          <div className="mb-6 p-5 rounded-2xl border border-primary/30 bg-primary/5 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Clock size={16} className="text-primary" /> Unsaved Campaign Draft
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                You have an unsaved workflow from {draftTime}.
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setConfirmModal({
                    isOpen: true,
                    title: "Discard Draft",
                    message: "Are you sure you want to permanently delete this unsaved draft?",
                    onConfirm: () => {
                      localStorage.removeItem("elein_unsaved_draft")
                      setDraftExists(false)
                      setConfirmModal(null)
                    }
                  });
                }}
                className="px-4 py-2 text-xs font-semibold text-destructive hover:text-destructive transition-colors"
              >
                Discard
              </button>
              {draftExists ? (
                <button
                  onClick={() => navigate("/elein/campaigns/new?resume=true")}
                  className="px-4 py-2 rounded-xl bg-primary hover:hover:bg-primary/90 text-white text-xs font-bold transition-all shadow-md"
                >
                  Resume Draft
                </button>
              ) : (
                <button
                  disabled
                  title="No saved draft"
                  className="px-4 py-2 rounded-xl bg-gray-400 text-white text-xs font-bold transition-all shadow-md cursor-not-allowed opacity-50"
                >
                  Resume Draft
                </button>
              )}
            </div>
          </div>
        )}
        
        {campaigns.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center justify-center p-12 rounded-3xl"
          >
            <h2 className="text-3xl font-light tracking-tight text-foreground mb-12">Start outreach</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-4xl">
              <EmptyCampaignCard 
                id="get_customers"
                icon={Users}
                title="Get customers"
                desc="Message people who can buy. Goal: book a meeting."
                onSelect={(id: string) => { resetTree(); navigate('/elein/campaigns/new?start=' + id); }}
              />
              <EmptyCampaignCard 
                id="hire_people"
                icon={Briefcase}
                title="Hire people"
                desc="Message people you want on the team. Goal: a hire."
                onSelect={(id: string) => { resetTree(); navigate('/elein/campaigns/new?start=' + id); }}
              />
              <EmptyCampaignCard 
                id="get_intros"
                icon={LinkIcon}
                title="Get intros"
                desc="Message people who can open a door — investor, partner, or their network."
                onSelect={(id: string) => { resetTree(); navigate('/elein/campaigns/new?start=' + id); }}
              />
            </div>
            
            
          </motion.div>
        ) : filtered.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center justify-center p-12 text-center rounded-3xl border border-border/50 bg-muted/30 dark:bg-background/50 backdrop-blur-md"
            >
              <div className="w-16 h-16 rounded-2xl bg-muted/40 border border-border flex items-center justify-center mb-6">
                <Search size={24} className="text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium text-foreground mb-2">No results found</h3>
              <p className="text-sm text-muted-foreground max-w-sm mb-6 leading-relaxed">
                We couldn't find any campaigns matching "{search}".
              </p>
            </motion.div>
          ) : (
            <div className="bg-background rounded-xl border border-border/60 overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-muted/30 border-b border-border/60 text-muted-foreground text-xs font-semibold">
                    <tr>
                      <th className="px-6 py-4 w-32">Status</th>
                      <th className="px-6 py-4 min-w-[200px]">Campaign</th>
                      <th className="px-6 py-4 w-64">Performance</th>
                      <th className="px-6 py-4 w-64">Progress</th>
                      <th className="px-6 py-4 w-32">Senders</th>
                      <th className="px-6 py-4 w-12"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    <AnimatePresence>
                    {filtered.map((c, i) => {
                      const statusCfg = STATUS_CONFIG[c.status] || STATUS_CONFIG["DRAFT"]
                      const leadCount = c.leads_total || 0
                      const running = c.leads_running || 0
                      const pending = c.leads_pending || 0
                      const completed = c.leads_completed || 0
                      const dateStr = c.created_at ? new Date(c.created_at).toLocaleString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit', hour: 'numeric', minute: '2-digit' }) : "Just now"

                      return (
                        <motion.tr
                          key={c.id}
                          className="hover:bg-muted/20 transition-colors group"
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, x: -16, transition: { duration: 0.2 } }}
                          transition={{ duration: 0.22, delay: i * 0.03 }}
                        >
                          {/* Status */}
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <div className={`w-1.5 h-1.5 rounded-full ${statusCfg.dot} shadow-sm`} />
                              <span className={`text-[11px] font-semibold tracking-wide uppercase ${statusCfg.text}`}>
                                {statusCfg.label}
                              </span>
                            </div>
                          </td>

                          {/* Campaign Name & Date */}
                          <td className="px-6 py-4">
                            <Link to={`/elein/campaigns/${c.id}`} className="block">
                              <p className="font-bold text-foreground text-sm hover:underline underline-offset-4">{c.name}</p>
                              <p className="text-[11px] text-muted-foreground mt-0.5">{dateStr}</p>
                            </Link>
                          </td>

                          {/* Performance Badges */}
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-muted/40 border border-border/40 text-[11px] font-medium text-foreground">
                                <Users size={12} className="text-muted-foreground" /> {leadCount}
                              </div>
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-muted/40 border border-border/40 text-[11px] font-medium text-foreground">
                                <Activity size={12} className="text-muted-foreground" /> {((c.conversion_rate ?? 0) * 100).toFixed(1)}%
                              </div>
                            </div>
                          </td>

                          {/* Progress Badges */}
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-muted/40 border border-border/40 text-[11px] font-medium text-foreground">
                                <Clock size={12} className="text-muted-foreground" /> {pending}
                              </div>
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-primary/10 border border-primary/20 text-[11px] font-medium text-primary">
                                <Activity size={12} /> {running}
                              </div>
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-success/10 border border-success/20 text-[11px] font-medium text-success">
                                <CheckCircle2 size={12} /> {completed}
                              </div>
                            </div>
                          </td>

                          {/* Senders */}
                          <td className="px-6 py-4 text-muted-foreground text-xs">
                            {c.senders && c.senders.length > 0 ? (
                              <div className="flex -space-x-2 overflow-hidden">
                                {c.senders.map((s: any, idx: number) => (
                                  <div key={idx} className="inline-block h-8 w-8 rounded-full ring-2 ring-background bg-primary/10 border border-primary/20 text-primary flex items-center justify-center text-xs font-bold shadow-sm" title={s.name}>
                                    {s.name.substring(0, 2).toUpperCase()}
                                  </div>
                                ))}
                              </div>
                            ) : (
                              "—"
                            )}
                          </td>

                          {/* Actions */}
                          <td className="px-6 py-4 text-right">
                            <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              {c.status !== "DRAFT" && (
                                <button
                                  onClick={() => toggleStatus(c.id)}
                                  className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
                                  title={c.status === "ACTIVE" ? "Pause" : "Resume"}
                                >
                                  {c.status === "ACTIVE" ? <Pause size={14} /> : <Play size={14} />}
                                </button>
                              )}
                              <button
                                onClick={() => navigate(`/elein/campaigns/new?edit=${c.id}`)}
                                className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
                                title="Edit Campaign"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                              </button>
                              <button
                                onClick={() => remove(c.id)}
                                className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </td>
                        </motion.tr>
                      )
                    })}
                    </AnimatePresence>
                  </tbody>
                </table>
              </div>
            </div>
          )}
      </>

      {/* Custom Confirmation Modal */}
      <AnimatePresence>
        {confirmModal && confirmModal.isOpen && (
          <motion.div
            key="confirm-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-sm bg-card border border-border rounded-2xl shadow-xl overflow-hidden"
            >
              <div className="p-6">
                <h3 className="text-lg font-semibold text-foreground mb-2">{confirmModal.title}</h3>
                <p className="text-sm text-muted-foreground">{confirmModal.message}</p>
              </div>
              <div className="px-6 py-4 bg-muted/30 border-t border-border flex items-center justify-end gap-3">
                <button 
                  onClick={() => setConfirmModal(null)}
                  className="px-4 py-2 rounded-xl text-sm font-medium hover:bg-muted text-foreground transition-colors"
                >
                  Cancel
                </button>
                <button 
                  onClick={confirmModal.onConfirm}
                  className="px-4 py-2 rounded-xl text-sm font-medium bg-destructive hover:bg-destructive/90 text-white transition-colors shadow-sm active:scale-95"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}