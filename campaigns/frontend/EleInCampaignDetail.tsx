import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { useState } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import useSWR from "swr"
import {
  ArrowLeft, Activity, Users, CheckCircle2,
  AlertTriangle, Clock, RefreshCw, Play, Pause, Search, LayoutDashboard
} from "lucide-react"
import { toast } from "sonner"
import { useEffect } from "react"
import { useHRTreeStore, dagToTree } from "@campaigns/eiTreeStore"
import { EISequenceTree } from "@/components/elein/EISequenceTree"
import { cn } from "@/lib/utils"



export function EleInCampaignDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: campaign, mutate, error } = useSWR(
    id ? `/api/elein/campaigns/${id}/detail` : null,
    fetcher
  )
  
  const { data: attribution } = useSWR(
    id ? `/api/elein/campaigns/${id}/attribution` : null,
    fetcher
  )

  const nodeAnalytics = attribution?.nodes?.reduce((acc: any, node: any) => {
    acc[node.node_id] = node
    return acc
  }, {})

  const { data: leads = [] } = useSWR(
    id ? `/api/elein/campaigns/${id}/leads` : null,
    fetcher
  )

  const [toggling, setToggling] = useState(false)
  const [search, setSearch] = useState("")

  useEffect(() => {
    if (campaign) {
      try {
        let nodes = campaign.nodes || (campaign.nodes_json ? (typeof campaign.nodes_json === "string" ? JSON.parse(campaign.nodes_json) : campaign.nodes_json) : []);
        let edges = campaign.edges || (campaign.edges_json ? (typeof campaign.edges_json === "string" ? JSON.parse(campaign.edges_json) : campaign.edges_json) : []);
        
        useHRTreeStore.getState().loadTree(dagToTree(nodes, edges))
      } catch (e) {
        console.error("Failed to parse campaign graph", e)
      }
    }
  }, [campaign?.id, typeof campaign?.nodes_json === "string" ? campaign.nodes_json : JSON.stringify(campaign?.nodes_json), typeof campaign?.edges_json === "string" ? campaign.edges_json : JSON.stringify(campaign?.edges_json)])


  const toggleStatus = async () => {
    if (!campaign) return
    setToggling(true)
    const action = campaign.status === 'ACTIVE' ? 'pause' : 'activate'
    try {
      await fetchWithAuth(`/api/elein/campaigns/${id}/${action}`, { method: 'PATCH' })
      toast.success(action === 'activate' ? "Campaign activated" : "Campaign paused")
      mutate()
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setToggling(false)
    }
  }

  if (error) {
    return (
      <div className="min-h-full flex items-center justify-center">
        <div className="text-center space-y-4">
          <AlertTriangle className="mx-auto h-8 w-8 text-muted-foreground" />
          <h2 className="text-lg font-medium text-foreground">Campaign not found</h2>
          <Link to="/elein/campaigns" className="text-sm text-primary hover:underline">
            Back to Campaigns
          </Link>
        </div>
      </div>
    )
  }

  if (!campaign) {
    return (
      <div className="min-h-full p-8 space-y-8 animate-pulse">
        <div className="flex gap-4">
          <div className="w-8 h-8 rounded bg-white/5" />
          <div className="h-8 w-64 rounded bg-white/5" />
        </div>
        <div className="grid grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-24 rounded-xl bg-white/5" />)}
        </div>
      </div>
    )
  }

  const filteredLeads = leads.filter((l: any) => 
    ((l.kdm_first || "") + " " + (l.kdm_last || "")).toLowerCase().includes(search.toLowerCase()) ||
    (l.company_name || "").toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="min-h-full max-w-7xl mx-auto p-8 space-y-10">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <Link to="/elein/campaigns" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft size={16} /> Back
          </Link>
          <div className="flex items-center gap-4">
            <h1 className="text-3xl font-bold tracking-tight text-foreground">{campaign.name}</h1>
            <span className={cn(
              "px-2.5 py-1 text-xs font-semibold uppercase tracking-wider rounded-full border flex items-center gap-1.5",
              campaign.status === 'ACTIVE' ? "bg-success/10 text-success border-success/20" :
              campaign.status === 'PAUSED' ? "bg-primary/10 text-primary/80 border-primary/20" :
              "bg-muted text-muted-foreground border-border"
            )}>
              {campaign.status === 'ACTIVE' && <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />}
              {campaign.status}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/elein/campaigns/new?edit=${campaign.id}`)}
            className="flex items-center gap-2 px-4 py-2 bg-muted/30 hover:bg-muted text-foreground font-medium text-sm rounded-lg transition-colors border border-border/50"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
            Edit
          </button>
          <button
            onClick={toggleStatus}
            disabled={toggling || campaign.status === 'DRAFT'}
            className="flex items-center gap-2 px-4 py-2 bg-foreground text-background hover:bg-foreground/90 font-medium text-sm rounded-lg transition-colors disabled:opacity-50"
          >
            {campaign.status === 'ACTIVE' ? <Pause size={16} /> : <Play size={16} />}
            {campaign.status === 'ACTIVE' ? 'Pause' : 'Start'}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: "Enrolled", value: campaign.stats?.total_leads ?? 0, icon: Users, color: "text-primary" },
          { label: "Running", value: campaign.stats?.running ?? 0, icon: Activity, color: "text-primary/80" },
          { label: "Completed", value: campaign.stats?.completed ?? 0, icon: CheckCircle2, color: "text-success" },
          { label: "Conversion", value: `${((campaign.stats?.conversion_rate ?? 0) * 100).toFixed(1)}%`, icon: RefreshCw, color: "text-primary" }
        ].map((stat, i) => (
          <div key={i} className="bg-black/20 border border-border p-5 rounded-xl flex items-center gap-4">
            <div className={cn("p-3 rounded-lg bg-white/5", stat.color)}>
              <stat.icon size={20} />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">{stat.label}</p>
              <h3 className="text-2xl font-semibold text-foreground mt-1 tabular-nums">{stat.value}</h3>
            </div>
          </div>
        ))}
      </div>

      {/* Accounts & Workflow Flow */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-black/20 border border-border rounded-xl p-6">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-6 flex items-center gap-2">
            <LayoutDashboard size={16} /> Workflow Logic
          </h3>
          <div className="flex items-center flex-wrap gap-3">
            {campaign.nodes && campaign.nodes.length > 0 ? (
              campaign.nodes.map((node: any, idx: number) => (
                <div key={node.id} className="flex items-center gap-3">
                  <div className="px-4 py-2.5 rounded-lg border border-border bg-white/5 text-sm font-medium text-foreground">
                    {node.data?.label || node.type}
                  </div>
                  {idx < campaign.nodes.length - 1 && (
                    <ArrowLeft size={16} className="text-muted-foreground rotate-180" />
                  )}
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No sequence steps defined.</p>
            )}
          </div>
        </div>

        <div className="bg-black/20 border border-border rounded-xl p-6">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-6">Senders</h3>
          <div className="space-y-3">
            {campaign.accounts && campaign.accounts.length > 0 ? (
              campaign.accounts.map((acc: any) => (
                <div key={acc.id} className="flex items-center gap-3 p-3 rounded-lg border border-white/5 bg-white/[0.02]">
                  <div className="w-8 h-8 rounded bg-primary/20 text-primary flex items-center justify-center font-bold text-xs uppercase">
                    {acc.name.substring(0, 2)}
                  </div>
                  <div className="truncate">
                    <p className="text-sm font-medium text-foreground truncate">{acc.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{acc.linkedin_profile_url || "No URL"}</p>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No accounts linked.</p>
            )}
          </div>
        </div>
      </div>

      
      {/* Campaign Analytics Tree */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-foreground">Sequence Flow</h3>
        <div className="border border-border rounded-xl bg-[url('/grid.svg')] bg-center bg-black/10 overflow-hidden relative h-[500px]">
          <div className="absolute inset-0 pointer-events-auto">
            <EISequenceTree readOnly={true} nodeAnalytics={nodeAnalytics} />
          </div>
        </div>
      </div>

      {/* Lead Matrix */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-foreground">Lead Matrix</h3>
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
            <input 
              type="text" 
              placeholder="Search leads..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-transparent border border-border rounded-lg text-sm text-foreground focus:outline-none focus:border-primary/50"
            />
          </div>
        </div>

        <div className="border border-border rounded-xl overflow-hidden">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-6 py-4 font-medium">Prospect</th>
                <th className="px-6 py-4 font-medium">Company</th>
                <th className="px-6 py-4 font-medium">Status</th>
                <th className="px-6 py-4 font-medium">Last Active</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-black/10">
              {filteredLeads.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-muted-foreground">
                    No leads found matching your search.
                  </td>
                </tr>
              ) : (
                filteredLeads.map((lead: any) => (
                  <tr key={lead.id} className="hover:bg-white/[0.02] transition-colors group">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-semibold text-foreground">
                          {(lead.kdm_first?.[0] || "") + (lead.kdm_last?.[0] || "")}
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{lead.kdm_first} {lead.kdm_last}</p>
                          <p className="text-xs text-muted-foreground truncate max-w-[200px]">{lead.job_title || "No Title"}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-muted-foreground">
                      {lead.company_name || "—"}
                    </td>
                    <td className="px-6 py-4">
                      <span className={cn(
                        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
                        lead.status === 'completed' ? "bg-success/10 text-success border-success/20" :
                        lead.status === 'error' ? "bg-destructive/10 text-destructive border-destructive/20" :
                        lead.status === 'running' ? "bg-primary/10 text-primary/80 border-primary/20" :
                        "bg-muted/50 text-muted-foreground border-transparent"
                      )}>
                        {lead.status === 'running' && <Clock size={12} />}
                        {lead.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-muted-foreground text-xs">
                      {new Date(lead.updated_at || lead.next_run_at || new Date().toISOString()).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
