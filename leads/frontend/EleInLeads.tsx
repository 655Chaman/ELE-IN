// ORCHESTRATOR: This file coordinates state only. Do NOT add UI rendering here. Add new UI sections as separate components in components/leads/
import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import { Database, Users } from "lucide-react"
import { toast } from "sonner"

import { supabase } from "@/lib/supabase"
import { fetcher } from "@/lib/apiClient"
import ShinyText from "@/components/ShinyText"

import type { LeadList } from "@/components/leads/leads.types"
import { LeadFilters } from "@/components/leads/LeadFilters"
import { LeadTable } from "@/components/leads/LeadTable"
import { ImportLeadsModal } from "@/components/leads/ImportLeadsModal"
import { ListLeadsDrawer } from "@/components/leads/ListLeadsDrawer"
import { DeleteConfirmationModal } from "@/components/leads/DeleteConfirmationModal"

export function EleInLeads() {
  const [search, setSearch] = useState("")
  const [listTypeFilter, setListTypeFilter] = useState("all")
  const [campaignFilter, setCampaignFilter] = useState("all")
  const [showModal, setShowModal] = useState(false)
  const [selectedList, setSelectedList] = useState<LeadList | null>(null)
  const [listToDelete, setListToDelete] = useState<LeadList | null>(null)

  const prevListsRef = useRef<Map<string, LeadList>>(new Map())
  const errorShownRef = useRef<Set<string>>(new Set())
  
  const { data: lists, error, isLoading, mutate } = useSWR<LeadList[]>('/api/elein/leads/lists', fetcher)
  
  const safeLists = Array.isArray(lists) ? lists : []

  useEffect(() => {
    if (!safeLists || safeLists.length === 0) return

    safeLists.forEach(list => {
      const prev = prevListsRef.current.get(list.id)
      
      if (prev && (prev.row_count === -1 || (prev as any).status === 'importing') && list.row_count === -2) {
        if (!errorShownRef.current.has(list.id)) {
          toast.error(`Import failed for ${list.name}. Please try re-uploading your CSV.`, { duration: 8000 })
          errorShownRef.current.add(list.id)
        }
      }
      
      prevListsRef.current.set(list.id, list)
    })
  }, [safeLists])
  
  useEffect(() => {
    const channel = supabase
      .channel('schema-db-changes')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'lead_lists' }, (payload) => {
        mutate(current => {
          if (!current) return [payload.new as LeadList]
          if (current.some(l => l.id === payload.new.id)) return current
          return [payload.new as LeadList, ...current]
        }, false)
      })
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'lead_lists' }, (payload) => {
        mutate(current => {
          if (!current) return current
          return current.map(l => l.id === payload.new.id ? { ...l, ...payload.new } : l)
        }, false)
      })
      .on('postgres_changes', { event: 'DELETE', schema: 'public', table: 'lead_lists' }, (payload) => {
        mutate(current => {
          if (!current) return current
          return current.filter(l => l.id !== payload.old.id)
        }, false)
      })
      .subscribe()
      
    return () => {
      supabase.removeChannel(channel)
    }
  }, [mutate])

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

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-8 py-10 max-w-5xl mx-auto font-sans">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-2xl font-bold mb-1">
          <ShinyText text="Leads" disabled={false} speed={3} className="" />
        </h1>
        <p className="text-xs text-muted-foreground mb-4">Manage your lead lists. Import from CSV, Sales Navigator, or paste LinkedIn URLs.</p>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-border/50 bg-background/50 backdrop-blur-md shadow-sm">
            <Database size={14} className="text-primary" />
            <span className="text-xs font-medium">{totalLists} {totalLists === 1 ? 'list' : 'lists'}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-border/50 bg-background/50 backdrop-blur-md shadow-sm">
            <Users size={14} className="text-primary" />
            <span className="text-xs font-medium">{totalLeads.toLocaleString()} {totalLeads === 1 ? 'lead' : 'leads'}</span>
          </div>
          {importingCount > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-border/50 bg-primary/10 text-primary backdrop-blur-md shadow-sm">
              <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span><span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span></span>
              <span className="text-xs font-medium">{importingCount} Importing</span>
            </div>
          )}
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <LeadFilters 
          search={search}
          setSearch={setSearch}
          listTypeFilter={listTypeFilter}
          setListTypeFilter={setListTypeFilter}
          campaignFilter={campaignFilter}
          setCampaignFilter={setCampaignFilter}
          onAddLeads={() => setShowModal(true)}
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
      />

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
