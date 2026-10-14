import React, { useState, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import { Users, X, Trash2, Search, Download, CheckSquare, Square, Check, AlertTriangle, Loader2, Lock, ArrowRight, Zap } from "lucide-react"
import { Linkedin } from "../icons/Linkedin"
import { toast } from "sonner"
import { friendlyToast } from "../FriendlyError"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import { TableSkeleton } from "../EleInSkeleton"
import { Virtuoso } from "react-virtuoso"

export function ListLeadsDrawer({ list, onClose, mutateLists }: { list: any; onClose: () => void; mutateLists: () => void }) {
  const { data: leads, error, isLoading, mutate } = useSWR(`/api/leads/lists/${list.id}/leads`, fetcher)
  const [search, setSearch] = useState("")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showConfirmDelete, setShowConfirmDelete] = useState(false)
  const [isBatchRemoving, setIsBatchRemoving] = useState(false)

  const { openPaywall } = usePaywall()
  const { data: billingData } = useSWR<{ tier?: string; tier_limits?: any }>('/api/elein/workspaces/billing', fetcher)
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'

  const leadList = leads?.data || []

  // Filtered leads based on search query
  const filteredLeads = useMemo(() => {
    if (!search.trim()) return leadList
    const q = search.toLowerCase()
    return leadList.filter((lead: any) => {
      const name = `${lead.first_name || ""} ${lead.last_name || ""}`.toLowerCase()
      const company = (lead.company_name || "").toLowerCase()
      const title = (lead.job_title || "").toLowerCase()
      return name.includes(q) || company.includes(q) || title.includes(q)
    })
  }, [leadList, search])

  const allFilteredSelected = filteredLeads.length > 0 && filteredLeads.every((l: any) => selectedIds.has(l.id))

  const toggleSelectAll = () => {
    if (allFilteredSelected) {
      setSelectedIds(new Set())
    } else {
      const next = new Set(selectedIds)
      filteredLeads.forEach((l: any) => next.add(l.id))
      setSelectedIds(next)
    }
  }

  const toggleLead = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const handleRemoveLead = async (leadId: string) => {
    const lead = leadList.find((l: any) => l.id === leadId)
    try {
      // Optimistic update
      mutate((current: any) => ({ ...current, data: current?.data?.filter((l: any) => l.id !== leadId) }), false)
      if (selectedIds.has(leadId)) {
        const next = new Set(selectedIds)
        next.delete(leadId)
        setSelectedIds(next)
      }
      await fetchWithAuth(`/api/leads/lists/${list.id}/leads/${leadId}`, { method: 'DELETE' })
      mutateLists()
      toast.success(`${lead?.first_name || 'Lead'} ${lead?.last_name || ''}`.trim() + ` removed from "${list.name}"`)
    } catch (e: any) {
      friendlyToast('Failed to remove lead — please try again.', e)
      mutate()
    }
  }

  const exportSelectedCsv = async () => {
    const toExport = selectedIds.size > 0 
      ? leadList.filter((l: any) => selectedIds.has(l.id))
      : filteredLeads
    if (toExport.length === 0) return

    // Paranoia Layer 1 & 2: Check plan limits
    if (!isPro && toExport.length > 25) {
      openPaywall({ featureName: "Unlimited Lead Export & Unmasked Contact Data" })
      toast.info(`Free plan allows exporting up to 25 sample leads with masked emails. Upgrade to Growth Pro to export all ${toExport.length} leads with full unmasked contacts.`)
      return
    }

    const cleanCsvCell = (val: any): string => {
      const s = String(val ?? '').trim()
      const escaped = s.replace(/"/g, '""')
      if (['=', '+', '-', '@', '\t', '\r'].includes(escaped[0])) {
        return `"'${escaped}"`
      }
      return `"${escaped}"`
    }

    try {
      const selectedQuery = selectedIds.size > 0 ? `?selected_ids=${Array.from(selectedIds).join(",")}` : ""
      const res = await fetchWithAuth(`/api/leads/lists/${list.id}/export${selectedQuery}`)
      if (res.ok) {
        const json = await res.json()
        const exportedData = json.data || []
        
        const headers = ["First Name", "Last Name", "Job Title", "Company", "LinkedIn URL", "Email"]
        const rows = exportedData.map((l: any) => [
          cleanCsvCell(l.first_name),
          cleanCsvCell(l.last_name),
          cleanCsvCell(l.job_title),
          cleanCsvCell(l.company_name),
          cleanCsvCell(l.linkedin_url),
          cleanCsvCell(l.email)
        ])
        const csvContent = [headers.join(','), ...rows.map((r: string[]) => r.join(','))].join('\n')
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.setAttribute('href', url)
        link.setAttribute('download', `${list.name || 'leads'}_export.csv`)
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)

        if (!isPro) {
          toast.success(`Exported ${exportedData.length} sample leads (Free Plan). Upgrade to Growth Pro for full unmasked email addresses.`)
        } else {
          toast.success(`Exported ${exportedData.length} leads to CSV`)
        }
      } else {
        // Fallback to client-side masked export if backend endpoint has temporary glitch
        const sliceData = !isPro ? toExport.slice(0, 25) : toExport
        const headers = ["First Name", "Last Name", "Job Title", "Company", "LinkedIn URL", "Email"]
        const rows = sliceData.map((l: any) => {
          let email = l.email || ''
          if (!isPro && email.includes('@')) {
            const parts = email.split('@')
            email = `${parts[0].slice(0, 2)}***@${parts[1]}`
          }
          return [
            cleanCsvCell(l.first_name),
            cleanCsvCell(l.last_name),
            cleanCsvCell(l.job_title),
            cleanCsvCell(l.company_name),
            cleanCsvCell(l.linkedin_url),
            cleanCsvCell(email)
          ]
        })
        const csvContent = [headers.join(','), ...rows.map((r: string[]) => r.join(','))].join('\n')
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.setAttribute('href', url)
        link.setAttribute('download', `${list.name || 'leads'}_export.csv`)
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        toast.success(`Exported ${sliceData.length} leads to CSV`)
      }
    } catch (e: any) {
      toast.error("Failed to export leads. Please try again.")
    }
  }

  const handleBatchRemove = async () => {
    const idsToRemove = Array.from(selectedIds)
    if (idsToRemove.length === 0) return
    setIsBatchRemoving(true)
    try {
      mutate((current: any) => ({
        ...current,
        data: current?.data?.filter((l: any) => !selectedIds.has(l.id))
      }), false)
      
      await Promise.all(
        idsToRemove.map(id => fetchWithAuth(`/api/leads/lists/${list.id}/leads/${id}`, { method: 'DELETE' }))
      )
      setSelectedIds(new Set())
      mutateLists()
      toast.success(`Removed ${idsToRemove.length} leads from "${list.name}"`)
      setShowConfirmDelete(false)
    } catch (e: any) {
      friendlyToast('Failed to remove some leads — please refresh.', e)
      mutate()
    } finally {
      setIsBatchRemoving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <motion.div 
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div 
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className="relative w-full max-w-2xl bg-card border-l border-border h-full flex flex-col shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/10">
          <div>
            <h2 className="text-xl font-bold text-card-foreground flex items-center gap-2">
              <Users size={20} className="text-primary" />
              {list.name}
            </h2>
            <p className="text-[12px] text-muted-foreground mt-0.5 font-medium">
              {list.row_count === -1 ? "Extracting leads..." : `${leadList.length} leads loaded • ${list.row_count} total`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={exportSelectedCsv}
              disabled={leadList.length === 0}
              className="px-3 py-1.5 rounded-lg border border-border text-xs font-semibold text-foreground hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
              title={!isPro ? "Free Plan: 25 Leads Sample. Upgrade for Unlimited & Unmasked." : "Export to CSV"}
            >
              {!isPro ? <Lock size={12} className="text-amber-500" /> : <Download size={13} />}
              <span>{!isPro ? "Export CSV (25 Free)" : "Export CSV"}</span>
            </button>
            <button onClick={onClose} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* In-situ Pay Ramp Banner inside Drawer */}
        {!isPro && (
          <div className="px-6 py-2.5 bg-gradient-to-r from-amber-500/10 via-sky-500/5 to-transparent border-b border-border/50 flex items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Lock size={12} className="text-amber-500 shrink-0" />
              <span>Free tier limits CSV exports to <strong>25 sample leads</strong> with masked emails.</span>
            </div>
            <button
              onClick={() => openPaywall({ featureName: "Unlimited Lead Export & Unmasked Contact Data" })}
              className="text-[11px] font-bold text-primary hover:underline flex items-center gap-1 shrink-0 cursor-pointer"
            >
              <span>Unlock Unlimited</span>
              <ArrowRight size={11} />
            </button>
          </div>
        )}

        {/* Search & Filter Bar */}
        {leadList.length > 0 && (
          <div className="px-6 py-3 border-b border-border/60 bg-muted/5 flex items-center justify-between gap-3">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search by name, company, or job title…"
                className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-border/80 bg-background text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
              {search && (
                <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  <X size={12} />
                </button>
              )}
            </div>

            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0 cursor-pointer"
            >
              {allFilteredSelected ? (
                <>
                  <CheckSquare size={14} className="text-primary" />
                  <span>Deselect All</span>
                </>
              ) : (
                <>
                  <Square size={14} />
                  <span>Select All ({filteredLeads.length})</span>
                </>
              )}
            </button>
          </div>
        )}

        {/* Leads Virtualized List */}
        <div className="flex-1 overflow-y-auto p-6 relative">
          {isLoading ? (
            <div className="space-y-3">
              <TableSkeleton rows={5} />
            </div>
          ) : error ? (
            <div className="p-6 text-center text-destructive">Failed to load leads.</div>
          ) : leadList.length === 0 ? (
            <div className="py-20 flex flex-col items-center justify-center text-muted-foreground border-2 border-dashed border-border/50 rounded-xl bg-muted/10">
              <Users size={32} className="opacity-20 mb-3" />
              <p className="text-sm font-medium">No leads found in this list.</p>
              <p className="text-xs mt-1">This list is currently empty.</p>
            </div>
          ) : filteredLeads.length === 0 ? (
            <div className="py-16 flex flex-col items-center justify-center text-muted-foreground text-center">
              <Search size={28} className="opacity-20 mb-2" />
              <p className="text-sm font-medium">No matching leads</p>
              <p className="text-xs mt-1">No leads matched "{search}"</p>
            </div>
          ) : (
            // PARANOIA FRAMEWORK: NEVER MAP MASSIVE ARRAYS DIRECTLY INTO THE DOM. ALWAYS USE VIRTUALIZATION TO PREVENT OOM CRASHES AT 10K+ SCALE.
            <div className="h-full w-full pb-16">
              <Virtuoso
                className="w-full h-full"
                data={filteredLeads}
                itemContent={(index, lead: any) => {
                  const isSelected = selectedIds.has(lead.id)
                  return (
                    <div 
                      key={lead.id}
                      onClick={() => toggleLead(lead.id)}
                      className={`flex items-center gap-3.5 p-3.5 mb-2.5 mx-1 rounded-xl border transition-all group relative cursor-pointer ${
                        isSelected 
                          ? "border-primary/50 bg-primary/5 shadow-sm" 
                          : "border-border/60 bg-background hover:bg-muted/40 hover:border-border"
                      }`}
                    >
                      {/* Checkbox */}
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); toggleLead(lead.id); }}
                        className="text-muted-foreground hover:text-primary transition-colors shrink-0"
                      >
                        {isSelected ? (
                          <CheckSquare size={16} className="text-primary" />
                        ) : (
                          <Square size={16} className="text-muted-foreground/50 group-hover:text-muted-foreground" />
                        )}
                      </button>

                      {/* Avatar */}
                      <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs shrink-0">
                        {lead.first_name?.[0]}{lead.last_name?.[0]}
                        {!lead.first_name && <Users size={13} />}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 truncate">
                            <p className="text-sm font-semibold text-foreground truncate">
                              {lead.first_name} {lead.last_name}
                            </p>
                            {lead.social_intent_score > 0 && (
                              <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold uppercase tracking-wider shrink-0 ${
                                lead.social_intent_tier === 'HOT'
                                  ? 'bg-red-500/15 text-red-400 border border-red-500/30'
                                  : lead.social_intent_tier === 'WARM'
                                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                                  : 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                              }`}>
                                {lead.social_intent_score} Intent
                              </span>
                            )}
                          </div>
                          {lead.linkedin_url && (
                            <a 
                              href={lead.linkedin_url} 
                              target="_blank" 
                              rel="noreferrer" 
                              onClick={(e) => e.stopPropagation()}
                              className="text-muted-foreground hover:text-primary transition-colors p-1"
                              title="Open LinkedIn Profile"
                            >
                              <Linkedin size={14} />
                            </a>
                          )}
                        </div>
                        <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                          {lead.job_title} {lead.company_name ? `at ${lead.company_name}` : ''}
                        </p>
                      </div>

                      {/* Single Delete */}
                      <button 
                        onClick={(e) => { e.stopPropagation(); handleRemoveLead(lead.id); }}
                        className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all cursor-pointer"
                        title="Remove from list"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )
                }}
              />
            </div>
          )}
        </div>

        {/* Sticky Batch Actions Dock (Transcript 1, Invention 2) */}
        <AnimatePresence>
          {selectedIds.size > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              className="absolute bottom-4 left-6 right-6 z-20 p-3 bg-card/95 backdrop-blur-md border border-border shadow-2xl rounded-2xl flex items-center justify-between gap-3"
            >
              <div className="flex items-center gap-2 pl-2">
                <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                <span className="text-xs font-bold text-foreground">
                  {selectedIds.size} lead{selectedIds.size !== 1 ? 's' : ''} selected
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={exportSelectedCsv}
                  className="px-3 py-1.5 rounded-xl border border-border text-xs font-semibold text-foreground hover:bg-muted transition-colors flex items-center gap-1.5 cursor-pointer"
                  title={!isPro && selectedIds.size > 25 ? "Free tier allows 25 export sample" : "Export Selected"}
                >
                  {!isPro && selectedIds.size > 25 ? <Lock size={12} className="text-amber-500" /> : <Download size={13} />}
                  <span>Export Selected {!isPro && selectedIds.size > 25 ? "(Pro Lock)" : ""}</span>
                </button>
                <button
                  onClick={() => setShowConfirmDelete(true)}
                  className="px-3.5 py-1.5 rounded-xl bg-destructive hover:bg-destructive/90 text-white text-xs font-bold transition-colors flex items-center gap-1.5 shadow-sm cursor-pointer"
                >
                  <Trash2 size={13} /> Remove ({selectedIds.size})
                </button>
                <button
                  onClick={() => setSelectedIds(new Set())}
                  className="px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  Clear
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Batch Delete Confirmation Modal (Paranoia Framework Layer 1 & 2) */}
        <AnimatePresence>
          {showConfirmDelete && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm">
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-card border border-border shadow-2xl rounded-2xl p-6 max-w-md w-full mx-4"
              >
                <div className="flex items-center gap-3 text-destructive mb-3">
                  <AlertTriangle size={24} />
                  <h3 className="text-lg font-bold text-foreground">Remove {selectedIds.size} Leads?</h3>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed mb-6">
                  Are you sure you want to remove <span className="font-semibold text-foreground">{selectedIds.size} leads</span> from <span className="font-semibold text-foreground">"{list.name}"</span>? This will not delete them from active campaigns.
                </p>
                <div className="flex items-center justify-end gap-3">
                  <button
                    onClick={() => setShowConfirmDelete(false)}
                    disabled={isBatchRemoving}
                    className="px-4 py-2 rounded-xl border border-border text-sm font-semibold text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleBatchRemove}
                    disabled={isBatchRemoving}
                    className="px-4 py-2 rounded-xl bg-destructive hover:bg-destructive/90 text-sm font-bold text-white transition-colors shadow-md flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    {isBatchRemoving ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    <span>{isBatchRemoving ? "Removing..." : "Remove Leads"}</span>
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
