import { motion } from "motion/react"
import { Users, FileSpreadsheet, Compass, Search, Link2, Trash2, ChevronRight, AlertCircle, Plus, Download } from "lucide-react"
import { TableSkeleton } from "../EleInSkeleton"
import SpotlightCard from "../SpotlightCard"
import type { LeadList } from "./leads.types"

const TYPE_LABEL: Record<string, string> = {
  csv: "CSV Upload",
  sales_nav: "Sales Navigator",
  search: "Search Builder",
  linkedin_url: "LinkedIn URLs",
  hubspot: "HubSpot",
}

const STATUS_BADGE: Record<string, { label: string; className: string; icon?: boolean; title?: string }> = {
  completed:       { label: "Completed",       className: "bg-success/10 text-success" },
  importing:       { label: "Importing…",      className: "bg-primary/10 text-primary animate-pulse" },
  throttled:       { label: "Throttled",       className: "bg-primary/10 text-warning" },
  daily_limit:     { label: "Daily Limit",     className: "bg-primary/10 text-destructive" },
  error:           { label: "Error",           className: "bg-destructive text-white shadow-sm flex items-center gap-1", icon: true, title: "Import failed. Click to retry or re-upload." },
  session_expired: { label: "Session Expired", className: "bg-destructive/10 text-destructive" },
}

interface LeadTableProps {
  lists: LeadList[]
  isLoading: boolean
  error: any
  mutate: () => void
  onAddLeads: () => void
  onSelectList: (list: LeadList) => void
  onDeleteList: (list: LeadList) => void
}

export function LeadTable({
  lists,
  isLoading,
  error,
  mutate,
  onAddLeads,
  onSelectList,
  onDeleteList
}: LeadTableProps) {
  if (error) {
    return (
      <div className="mb-6 flex items-center justify-between p-3 rounded-lg border border-primary/20 bg-primary/10 text-warning">
        <div className="flex items-center gap-2 text-sm font-medium">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          {error instanceof Error ? error.message : String(error) || "Backend connection lost. Retrying..."}
        </div>
        <button onClick={() => mutate()} className="text-xs font-bold hover:underline">Reconnect</button>
      </div>
    )
  }

  if (isLoading && lists.length === 0) {
    return <TableSkeleton rows={5} />
  }

  if (lists.length === 0) {
    return (
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <SpotlightCard className="flex flex-col items-center justify-center py-24 border border-border/50 bg-background/50 text-center px-8">
          <div className="w-16 h-16 rounded-2xl border border-border/50 bg-muted/50 flex items-center justify-center mb-6 backdrop-blur-sm">
            <Users size={24} className="text-primary" />
          </div>
          <h2 className="text-xl font-light tracking-tight text-foreground mb-2">
            Who do you want to reach?
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-md mb-2">
            Import your targets from a CSV, paste LinkedIn URLs, or sync from Sales Navigator.
            We validate and prepare them for outreach automatically.
          </p>
          <a
            href="/template_leads.csv"
            download
            className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors mb-8"
          >
            <Download size={11} /> Download CSV template
          </a>
          <button 
            onClick={onAddLeads}
            className="flex items-center gap-2 px-6 py-3 bg-primary hover:bg-primary/90 rounded-xl text-sm font-bold text-primary-foreground transition-all shadow-sm"
          >
            <Plus size={14} /> Import a lead list
          </button>
        </SpotlightCard>
      </motion.div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-4 mt-2">
        <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Showing {lists.length} list{lists.length !== 1 ? 's' : ''}</span>
      </div>
      {lists.map((list, i) => (
        <motion.div
          key={list.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06 }}
        >
          <SpotlightCard className="relative overflow-hidden flex items-center gap-4 px-5 py-4 border border-border/50 bg-background/50 backdrop-blur-md cursor-pointer hover:border-primary/30 transition-transform hover:scale-[1.005] group" onClick={() => onSelectList(list)}>
            <div className={`w-10 h-10 rounded-lg border flex items-center justify-center shrink-0 ${(() => {
              switch(list.type) {
                case 'csv': return 'text-success bg-success/10 border-success/20';
                case 'sales_nav': return 'text-primary bg-primary/10 border-primary/20';
                case 'search': return 'text-primary bg-primary/10 border-primary/20';
                case 'linkedin_url': return 'text-primary bg-primary/10 border-primary/20';
                case 'hubspot': return 'text-primary bg-primary/10 border-primary/20';
                default: return 'text-primary bg-primary/10 border-primary/20';
              }
            })()}`}>
              {(() => {
                if ((list as any).status === 'importing' || list.row_count === -1) return <div className="animate-pulse"><Users size={16} /></div>;
                switch(list.type) {
                  case 'csv': return <FileSpreadsheet size={16} />;
                  case 'sales_nav': return <Compass size={16} />;
                  case 'search': return <Search size={16} />;
                  case 'linkedin_url': return <Link2 size={16} />;
                  default: return <Users size={16} />;
                }
              })()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-[15px] font-bold text-foreground">{list.name}</p>
                {(() => {
                  const st = (list as any).status || (list.row_count === -1 ? 'importing' : list.row_count === -2 ? 'error' : 'completed')
                  const badge = STATUS_BADGE[st]
                  if (!badge || st === 'completed') return null
                  return (
                    <span 
                      title={badge.title} 
                      className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${badge.className}`}
                    >
                      {badge.icon && <AlertCircle size={10} />}
                      {badge.label}
                    </span>
                  )
                })()}
              </div>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-[11px] font-medium text-muted-foreground">{TYPE_LABEL[list.type] || list.type}</span>
                <span className="text-[11px] text-muted-foreground/30">•</span>
                <span className="text-[11px] font-medium text-muted-foreground">
                  {(() => {
                    const st = (list as any).status || (list.row_count === -1 ? 'importing' : list.row_count === -2 ? 'error' : 'completed')
                    if (st === 'importing') return (
                      <span className="flex items-center gap-1.5 text-primary font-semibold">
                        <span className="relative flex h-1.5 w-1.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span><span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary"></span></span>
                        {list.type === "csv" ? "Processing CSV..." : "Extracting profiles..."}
                      </span>
                    )
                    if (st === 'throttled') return <span className="flex items-center gap-1.5 text-warning"><AlertCircle size={11} /> LinkedIn throttled — will retry</span>
                    if (st === 'daily_limit') return <span className="flex items-center gap-1.5 text-destructive"><AlertCircle size={11} /> Daily limit reached</span>
                    if (st === 'session_expired') return <span className="flex items-center gap-1.5 text-destructive"><AlertCircle size={11} /> LinkedIn session expired — reconnect account</span>
                    if (st === 'error') return <span className="flex items-center gap-1.5 text-destructive"><AlertCircle size={11} /> {(list as any).error_message || "Import failed. Please retry."}</span>
                    if (st.startsWith('completed') && st.includes('duplicates')) return <span className="text-muted-foreground">{list.row_count.toLocaleString()} leads <span className="text-warning">· {st.split('—')[1]?.trim()}</span></span>
                    return `${list.row_count.toLocaleString()} leads`
                  })()}
                </span>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 pr-2 relative z-10">
              <span className="text-[11px] text-muted-foreground font-medium">
                {new Date(list.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); onDeleteList(list); }}
                className="p-2 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
              >
                <Trash2 size={16} />
              </button>
            </div>
            
            <ChevronRight size={18} className="text-muted-foreground opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300 absolute right-4" />
            
            {(list.row_count === -1 || list.row_count < -2) && (
              <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-muted/30 overflow-hidden">
                <motion.div 
                  className="h-full bg-primary"
                  initial={{ x: "-100%" }}
                  animate={{ x: "100%" }}
                  transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
                />
              </div>
            )}
          </SpotlightCard>
        </motion.div>
      ))}
    </div>
  )
}
