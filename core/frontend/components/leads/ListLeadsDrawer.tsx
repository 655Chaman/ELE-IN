import { motion } from "motion/react"
import useSWR from "swr"
import { Users, X, Trash2 } from "lucide-react"
import { Linkedin } from "../icons/Linkedin"
import { toast } from "sonner"
import { friendlyToast } from "../FriendlyError"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { TableSkeleton } from "../EleInSkeleton"
import { Virtuoso } from "react-virtuoso"

export function ListLeadsDrawer({ list, onClose, mutateLists }: { list: any; onClose: () => void; mutateLists: () => void }) {
  const { data: leads, error, isLoading, mutate } = useSWR(`/api/leads/lists/${list.id}/leads`, fetcher)

  const handleRemoveLead = async (leadId: string) => {
    try {
      // Optimistic update
      mutate((current: any) => current?.filter((l: any) => l.id !== leadId), false)
      
      await fetchWithAuth(`/api/leads/lists/${list.id}/leads/${leadId}`, { method: 'DELETE' })
      mutateLists() // Note: the realtime channel will also update lists, but doing it here is fine.
      toast.success("Lead removed from list")
    } catch (e: any) {
      friendlyToast('Failed to remove lead — please try again.', e)
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <motion.div 
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div 
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className="relative w-full max-w-2xl bg-card border-l border-border h-full flex flex-col shadow-2xl"
      >
        <div className="flex items-center justify-between px-6 py-5 border-b border-border bg-muted/10">
          <div>
            <h2 className="text-xl font-bold text-card-foreground flex items-center gap-2">
              <Users size={20} className="text-primary" />
              {list.name}
            </h2>
            <p className="text-[12px] text-muted-foreground mt-1 font-medium">{list.row_count === -1 ? "Extracting leads..." : `${list.row_count} leads in this list`}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-all">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="space-y-3">
              <TableSkeleton rows={5} />
            </div>
          ) : error ? (
            <div className="p-6 text-center text-destructive">Failed to load leads.</div>
          ) : leads?.length === 0 ? (
            <div className="py-20 flex flex-col items-center justify-center text-muted-foreground border-2 border-dashed border-border/50 rounded-xl bg-muted/10">
              <Users size={32} className="opacity-20 mb-3" />
              <p className="text-sm font-medium">No leads found in this list.</p>
              <p className="text-xs mt-1">This list is currently empty.</p>
            </div>
          ) : (
            // PARANOIA FRAMEWORK: NEVER MAP MASSIVE ARRAYS DIRECTLY INTO THE DOM. ALWAYS USE VIRTUALIZATION TO PREVENT OOM CRASHES AT 10K+ SCALE.
            <div className="h-full w-full">
              <Virtuoso
                className="w-full h-full"
                data={leads}
                itemContent={(index, lead: any) => (
                  <div className="flex items-center gap-4 p-4 mb-3 mx-1 rounded-xl border border-border/50 bg-background hover:bg-muted/40 transition-all group relative">
                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                      {lead.first_name?.[0]}{lead.last_name?.[0]}
                      {!lead.first_name && <Users size={14} />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-foreground truncate">
                          {lead.first_name} {lead.last_name}
                        </p>
                        {lead.linkedin_url && (
                          <a href={lead.linkedin_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-primary transition-colors">
                            <Linkedin size={14} />
                          </a>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                        {lead.job_title} {lead.company_name ? `at ${lead.company_name}` : ''}
                      </p>
                    </div>
                    <button 
                      onClick={() => handleRemoveLead(lead.id)}
                      className="opacity-0 group-hover:opacity-100 p-2 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              />
            </div>
          )}
        </div>
      </motion.div>

    </div>
  )
}
