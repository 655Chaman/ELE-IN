// ORCHESTRATOR: This file coordinates state only. Do NOT add UI rendering here. Add new UI sections as separate components in components/leads/
import { useState, useEffect, useRef, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import { Database, Users, AlertTriangle, ArrowRight, Zap, Radio, Flame, Brain, Mic, Sliders, Building2, Repeat, Target, Calendar, Workflow, Link2, Rocket, Sparkles, ChevronDown } from "lucide-react"
import { toast } from "sonner"
import { usePaywall } from "@/contexts/PaywallContext"

import { supabase } from "@/lib/supabase"
import { fetcher } from "@/lib/apiClient"
import { ElesiumLogo } from "@/components/ElesiumLogo"

import type { LeadList } from "@/components/leads/leads.types"
import { LeadFilters } from "@/components/leads/LeadFilters"
import { LeadTable } from "@/components/leads/LeadTable"
import { ImportLeadsModal } from "@/components/leads/ImportLeadsModal"
import { ListLeadsDrawer } from "@/components/leads/ListLeadsDrawer"
import { DeleteConfirmationModal } from "@/components/leads/DeleteConfirmationModal"
import { SocialSignalRadarView } from "@/components/leads/SocialSignalRadarView"
import { PreWarmStudioModal } from "@/components/campaigns/PreWarmStudioModal"
import { BanditOptimizerStudioModal } from "@/components/campaigns/BanditOptimizerStudioModal"
import { EventMultimodalStudioModal } from "@/components/campaigns/EventMultimodalStudioModal"
import { DynamicSegmentationStudioModal } from "@/components/leads/DynamicSegmentationStudioModal"
import { AbmMultithreadStudioModal } from "@/components/campaigns/AbmMultithreadStudioModal"
import { BoomerangRevivalStudioModal } from "@/components/campaigns/BoomerangRevivalStudioModal"
import { OmnichannelRetargetingStudioModal } from "@/components/campaigns/OmnichannelRetargetingStudioModal"
import { DisplacementStudioModal } from "@/components/campaigns/DisplacementStudioModal"
import { CalendarConciergeStudioModal } from "@/components/campaigns/CalendarConciergeStudioModal"
import { WaterfallEnrichmentStudioModal } from "@/components/campaigns/WaterfallEnrichmentStudioModal"
import { WarmupStudioModal } from "@/components/campaigns/WarmupStudioModal"
import { CrmAttributionStudioModal } from "@/components/campaigns/CrmAttributionStudioModal"
import { AdvocacyPodStudioModal } from "@/components/campaigns/AdvocacyPodStudioModal"
import { useWorkspace } from "@/contexts/WorkspaceContext"

const STUDIOS = [
  {
    category: "Outreach & Signals",
    items: [
      { id: "prewarm", label: "Pre-Warm & Omnichannel", desc: "Multi-touch pre-warming & cadence setup", icon: Zap, iconColor: "text-amber-400" },
      { id: "segmentation", label: "Smart Segmentation", desc: "Dynamic rules & auto-enrollment triggers", icon: Sliders, iconColor: "text-primary" },
      { id: "abm", label: "ABM Multithreading", desc: "Map buying committees & multiple stakeholders", icon: Building2, iconColor: "text-amber-400" },
      { id: "displacement", label: "Displacement Radar", desc: "Target competitor contracts & renewals", icon: Target, iconColor: "text-indigo-400" },
    ]
  },
  {
    category: "Optimization & AI",
    items: [
      { id: "bandit", label: "Bandit & Trigger Studio", desc: "Multi-armed bandit variant optimization", icon: Brain, iconColor: "text-blue-400" },
      { id: "events", label: "Event & Voice Studio", desc: "Multimodal audio drops & event signals", icon: Mic, iconColor: "text-indigo-400" },
      { id: "waterfall", label: "Waterfall Enrichment", desc: "Multi-provider contact verification cascade", icon: Workflow, iconColor: "text-cyan-400" },
      { id: "boomerang", label: "Boomerang & Revival", desc: "Automated recycling of dormant pipeline", icon: Repeat, iconColor: "text-emerald-400" },
    ]
  },
  {
    category: "Infrastructure & CRM",
    items: [
      { id: "warmup", label: "Email Warmup & DNS", desc: "Deliverability pools & DNS verification", icon: Flame, iconColor: "text-amber-400" },
      { id: "crm", label: "CRM Sync & Attribution", desc: "Bidirectional sync with HubSpot & Salesforce", icon: Link2, iconColor: "text-cyan-400" },
      { id: "calendar", label: "Calendar Concierge", desc: "High-conversion scheduling links", icon: Calendar, iconColor: "text-emerald-400" },
      { id: "advocacy", label: "Advocacy Pods", desc: "Internal team engagement orchestration", icon: Rocket, iconColor: "text-blue-400" },
    ]
  }
]

export function EleInLeads() {
  const [activeTab, setActiveTab] = useState<"lists" | "radar" | "prewarm" | "bandit" | "events" | "segmentation" | "abm" | "boomerang" | "omnichannel" | "displacement" | "calendar" | "waterfall" | "warmup" | "crm" | "advocacy">("lists")
  const [segmentationListId, setSegmentationListId] = useState<string | undefined>(undefined)
  const [isStudiosOpen, setIsStudiosOpen] = useState(false)
  const studiosMenuRef = useRef<HTMLDivElement>(null)
  const [search, setSearch] = useState("")
  const [listTypeFilter, setListTypeFilter] = useState("all")
  const [campaignFilter, setCampaignFilter] = useState("all")
  const [showModal, setShowModal] = useState(false)
  const [selectedList, setSelectedList] = useState<LeadList | null>(null)
  const [listToDelete, setListToDelete] = useState<LeadList | null>(null)

  const prevListsRef = useRef<Map<string, LeadList>>(new Map())
  const errorShownRef = useRef<Set<string>>(new Set())
  
  const { data: lists, error, isLoading, mutate } = useSWR<LeadList[]>(
    '/api/elein/leads/lists', 
    fetcher,
    {
      refreshInterval: (latestData?: LeadList[]) => (latestData || []).some((l: any) => l.row_count === -1 || l.status === 'importing' || l.status === 'processing') ? 3000 : 0
    }
  )
  const { data: radarData } = useSWR<{ feed?: any[]; total_items?: number }>('/api/leads/social-radar/feed', fetcher)
  const { openPaywall } = usePaywall()
  const { data: billingData } = useSWR<{ tier?: string; tier_limits?: any }>('/api/elein/workspaces/billing', fetcher)
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'
  
  const safeLists = Array.isArray(lists) ? lists : []
  const hotCount = useMemo(() => {
    return (radarData?.feed || []).filter((f: any) => f.lead?.social_intent_tier === 'HOT').length
  }, [radarData])

  useEffect(() => {
    if (!safeLists || safeLists.length === 0) return

    safeLists.forEach(list => {
      const prev = prevListsRef.current.get(list.id)
      
      const prevWasImporting = prev?.row_count === -1 || (prev as any)?.status === 'importing' || (prev as any)?.status === 'processing';
      const isNowCompleted = list.row_count >= 0 && ((list as any).status === 'completed' || ((list as any).status && !(list as any).status.includes('error')));
      const isNowError = list.row_count === -2 || (list as any).status === 'error' || (list as any).status === 'failed';

      if (prev && prevWasImporting && isNowCompleted) {
        toast.success(`"${list.name}" imported with ${list.row_count.toLocaleString()} leads!`, { duration: 5000 })
      } else if (prev && prevWasImporting && isNowError) {
        if (!errorShownRef.current.has(list.id)) {
          toast.error(`Import failed for "${list.name}". Please check the file formatting and try again.`, { duration: 8000 })
          errorShownRef.current.add(list.id)
        }
      }
      
      prevListsRef.current.set(list.id, list)
    })
  }, [safeLists])
  
  const { activeWorkspaceId } = useWorkspace()

  useEffect(() => {
    const channel = supabase
      .channel(`schema-db-changes-${activeWorkspaceId || 'global'}`)
      .on('postgres_changes', { 
        event: 'INSERT', 
        schema: 'public', 
        table: 'lead_lists',
        filter: activeWorkspaceId ? `workspace_id=eq.${activeWorkspaceId}` : undefined
      }, (payload) => {
        mutate(current => {
          if (!current) return [payload.new as LeadList]
          if (current.some(l => l.id === payload.new.id)) return current
          return [payload.new as LeadList, ...current]
        }, false)
      })
      .on('postgres_changes', { 
        event: 'UPDATE', 
        schema: 'public', 
        table: 'lead_lists',
        filter: activeWorkspaceId ? `workspace_id=eq.${activeWorkspaceId}` : undefined
      }, (payload) => {
        mutate(current => {
          if (!current) return current
          return current.map(l => l.id === payload.new.id ? { ...l, ...payload.new } : l)
        }, false)
      })
      .on('postgres_changes', { 
        event: 'DELETE', 
        schema: 'public', 
        table: 'lead_lists',
        filter: activeWorkspaceId ? `workspace_id=eq.${activeWorkspaceId}` : undefined
      }, (payload) => {
        mutate(current => {
          if (!current) return current
          return current.filter(l => l.id !== payload.old.id)
        }, false)
      })
      .subscribe()
      
    return () => {
      supabase.removeChannel(channel)
    }
  }, [mutate, activeWorkspaceId])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (studiosMenuRef.current && !studiosMenuRef.current.contains(event.target as Node)) {
        setIsStudiosOpen(false)
      }
    }
    if (isStudiosOpen) {
      document.addEventListener("mousedown", handleClickOutside)
      return () => document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [isStudiosOpen])

  const filtered = safeLists.filter(l => {
    const matchesSearch = l.name.toLowerCase().includes(search.toLowerCase())
    const matchesType = listTypeFilter === "all" || l.type === listTypeFilter
    let matchesCampaign = true;
    if (campaignFilter !== "all") {
      if (campaignFilter === "unassigned") matchesCampaign = !l.campaign;
      else if (campaignFilter === "assigned") matchesCampaign = !!l.campaign;
    }
    return matchesSearch && matchesType && matchesCampaign
  })

  const totalLists = safeLists.length;
  const totalLeads = safeLists.reduce((acc, l) => acc + (l.row_count > 0 ? l.row_count : 0), 0);
  const importingCount = safeLists.filter(l => (l as any).status === 'importing' || l.row_count === -1).length;

  const typeCounts = useMemo(() => {
    const counts = { all: safeLists.length, csv: 0, sales_nav: 0, search: 0, linkedin_url: 0 }
    safeLists.forEach(l => {
      if (l.type && (counts as any)[l.type] !== undefined) {
        (counts as any)[l.type]++
      }
    })
    return counts
  }, [safeLists])

  const campaignCounts = useMemo(() => {
    let assigned = 0
    let unassigned = 0
    safeLists.forEach(l => {
      if (l.campaign) assigned++
      else unassigned++
    })
    return { all: safeLists.length, assigned, unassigned }
  }, [safeLists])

  const totalFilteredLeads = useMemo(() => {
    return filtered.reduce((acc, l) => acc + (l.row_count > 0 ? l.row_count : 0), 0)
  }, [filtered])

  const failedLists = useMemo(() => {
    return safeLists.filter(l => (l as any).status === 'error' || (l as any).status === 'failed' || l.row_count === -2)
  }, [safeLists])

  const handleRetryList = (list: LeadList) => {
    if (list.type === 'csv') {
      toast.info(`Opening import modal to re-upload "${list.name}".`)
      setShowModal(true)
    } else {
      toast.info(`Opening setup to re-run import for "${list.name}".`)
      setShowModal(true)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-4 sm:px-8 py-8 sm:py-10 max-w-5xl mx-auto font-sans">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Leads
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Manage your lead lists, prospect feeds, and multichannel audience segments.
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm text-xs text-muted-foreground shadow-xs">
              <Database size={13} className="text-primary" />
              <span><strong className="text-foreground font-semibold">{totalLists}</strong> {totalLists === 1 ? 'list' : 'lists'}</span>
              <span className="text-border">•</span>
              <Users size={13} className="text-primary" />
              <span><strong className="text-foreground font-semibold">{totalLeads.toLocaleString()}</strong> leads</span>
            </div>
            {importingCount > 0 && (
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border border-primary/30 bg-primary/10 text-primary text-xs font-medium animate-pulse shadow-xs">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                </span>
                <span>{importingCount} importing</span>
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* Navigation Tabs: Lists vs Social Signal Radar + Growth Studios Dropdown */}
      <div className="flex items-center justify-between gap-3 mb-6">
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-muted/40 border border-border/50">
          <button
            onClick={() => setActiveTab("lists")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "lists"
                ? "bg-card text-foreground shadow-xs border border-border/60"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Database size={13} className={activeTab === "lists" ? "text-primary" : ""} />
            <span>Lead Lists</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded-md bg-muted font-mono text-muted-foreground">
              {totalLists}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("radar")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "radar"
                ? "bg-card text-foreground shadow-xs border border-border/60"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Radio size={13} className={activeTab === "radar" ? "text-primary animate-pulse" : ""} />
            <span>Social Signal Radar</span>
            {hotCount > 0 ? (
              <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.2 rounded-md bg-red-500/15 text-red-400 border border-red-500/30 font-bold">
                <Flame size={10} />
                <span>{hotCount} Hot</span>
              </span>
            ) : (
              <span className="text-[10px] px-1.5 py-0.2 rounded-md bg-primary/10 text-primary font-bold">
                Intent
              </span>
            )}
          </button>
        </div>

        {/* Growth Studios Dropdown */}
        <div className="relative" ref={studiosMenuRef}>
          <button
            type="button"
            onClick={() => setIsStudiosOpen(!isStudiosOpen)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl border border-border/60 bg-card/60 hover:bg-card/90 text-xs font-semibold text-foreground transition-all shadow-xs cursor-pointer"
          >
            <Sparkles size={13} className="text-primary" />
            <span>Growth Studios</span>
            <ChevronDown size={13} className={`text-muted-foreground transition-transform duration-200 ${isStudiosOpen ? 'rotate-180' : ''}`} />
          </button>

          {isStudiosOpen && (
            <div className="absolute right-0 top-full mt-2 w-80 sm:w-96 rounded-xl border border-border/80 bg-popover/95 backdrop-blur-xl shadow-xl z-50 p-2.5 animate-in fade-in-0 zoom-in-95 duration-150">
              <div className="px-2.5 py-2 border-b border-border/40 mb-1 flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold text-foreground">Lead Intelligence & Growth Studios</h4>
                  <p className="text-[10px] text-muted-foreground">Advanced pipeline orchestration and signal engines</p>
                </div>
              </div>

              <div className="max-h-[380px] overflow-y-auto space-y-3 p-1">
                {STUDIOS.map((group) => (
                  <div key={group.category}>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/60 px-2 flex items-center gap-1.5 mb-1">
                      {group.category.includes("AI") && <ElesiumLogo size={11} />}
                      {group.category}
                    </span>
                    <div className="space-y-0.5">
                      {group.items.map((item) => {
                        const Icon = item.icon
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => {
                              if (item.id === "segmentation") {
                                setSegmentationListId(undefined)
                              }
                              setActiveTab(item.id as any)
                              setIsStudiosOpen(false)
                            }}
                            className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-xl text-left hover:bg-muted/50 transition-colors cursor-pointer group"
                          >
                            <div className="p-1.5 rounded-lg bg-background border border-border/50 shrink-0 mt-0.5">
                              <Icon size={13} className={item.iconColor} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-xs font-medium text-foreground group-hover:text-primary transition-colors">
                                {item.label}
                              </div>
                              <div className="text-[10px] text-muted-foreground leading-snug truncate">
                                {item.desc}
                              </div>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {activeTab === "advocacy" ? (
        <AdvocacyPodStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "crm" ? (
        <CrmAttributionStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "warmup" ? (
        <WarmupStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "waterfall" ? (
        <WaterfallEnrichmentStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "calendar" ? (
        <CalendarConciergeStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "displacement" ? (
        <DisplacementStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "omnichannel" ? (
        <OmnichannelRetargetingStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "boomerang" ? (
        <BoomerangRevivalStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "abm" ? (
        <AbmMultithreadStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "segmentation" ? (
        <DynamicSegmentationStudioModal 
          initialListId={segmentationListId}
          onClose={() => setActiveTab("lists")} 
          onRulesSaved={() => mutate()}
        />
      ) : activeTab === "events" ? (
        <EventMultimodalStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "bandit" ? (
        <BanditOptimizerStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "prewarm" ? (
        <PreWarmStudioModal onClose={() => setActiveTab("lists")} />
      ) : activeTab === "radar" ? (
        <SocialSignalRadarView onSwitchToLists={() => setActiveTab("lists")} />
      ) : (
        <>
          {/* In-Situ Pay Ramp: Lead Intelligence & Unlimited Export */}
          {!isPro && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 p-3.5 sm:p-4 rounded-xl bg-card/40 border border-emerald-500/20 shadow-xs relative overflow-hidden flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                  <Database className="w-4 h-4 text-emerald-400" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground">Free Lead Intelligence</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      25 Sample Exports
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5 max-w-xl">
                    Free plan includes 25 sample leads with masked contacts. Upgrade to <strong>Growth Pro</strong> for unlimited CSV exports with verified emails & direct dials.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Unlimited Lead Export & Unmasked Contact Data" })}
                className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-xs transition-all cursor-pointer whitespace-nowrap self-start sm:self-auto shrink-0"
              >
                <Zap size={12} className="fill-current" />
                <span>Upgrade to Pro</span>
                <ArrowRight size={12} />
              </button>
            </motion.div>
          )}

          {/* Global Failed Imports Attention Banner (Layer 1 & Layer 2) */}
          {failedLists.length > 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-sm"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0">
                  <AlertTriangle size={16} />
                </div>
                <div>
                  <span className="font-bold text-foreground block">
                    {failedLists.length} Lead List Import{failedLists.length > 1 ? "s" : ""} Encountered Errors
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {failedLists.map(f => f.name).slice(0, 2).join(", ")}{failedLists.length > 2 ? ` and ${failedLists.length - 2} more` : ""} stopped during processing. Click retry to recover.
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowModal(true)}
                className="px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold transition-all shrink-0 flex items-center gap-1.5 self-start sm:self-auto shadow-xs"
              >
                <span>Re-Import / Fix</span>
                <ArrowRight size={13} />
              </button>
            </motion.div>
          )}

          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <LeadFilters 
              search={search}
              setSearch={setSearch}
              listTypeFilter={listTypeFilter}
              setListTypeFilter={setListTypeFilter}
              campaignFilter={campaignFilter}
              setCampaignFilter={setCampaignFilter}
              onAddLeads={() => setShowModal(true)}
              typeCounts={typeCounts}
              campaignCounts={campaignCounts}
              totalFilteredLeads={totalFilteredLeads}
              totalFilteredLists={filtered.length}
            />
          </motion.div>

          <LeadTable 
            lists={filtered}
            isLoading={isLoading}
            error={error}
            mutate={mutate}
            onAddLeads={() => setShowModal(true)}
            onSelectList={setSelectedList}
            onDeleteList={setListToDelete}
            onRetryList={handleRetryList}
            onOpenSegmentation={(list) => {
              setSegmentationListId(list.id);
              setActiveTab("segmentation");
            }}
          />
        </>
      )}

      <AnimatePresence>
        {showModal && (
          <ImportLeadsModal onClose={() => setShowModal(false)} onAdd={() => mutate()} />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {selectedList && (
          <ListLeadsDrawer list={selectedList} onClose={() => setSelectedList(null)} mutateLists={mutate} />
        )}
      </AnimatePresence>
      
      <AnimatePresence>
        {listToDelete && (
          <DeleteConfirmationModal list={listToDelete} onClose={() => setListToDelete(null)} onConfirm={() => mutate()} />
        )}
      </AnimatePresence>
    </div>
  )
}
