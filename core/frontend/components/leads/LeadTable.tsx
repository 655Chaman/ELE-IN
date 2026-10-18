import { motion, AnimatePresence } from "motion/react"
import { Users, FileSpreadsheet, Compass, Search, Link2, Trash2, ChevronRight, AlertCircle, Plus, Download, RotateCw, Sliders } from "lucide-react"
import { TableSkeleton } from "../EleInSkeleton"
import type { LeadList } from "./leads.types"

const TYPE_LABEL: Record<string, string> = {
  csv: "CSV Upload",
  sales_nav: "Sales Navigator",
  search: "Search Builder",
  linkedin_url: "LinkedIn URLs",
  hubspot: "HubSpot",
  dynamic: "Dynamic Segment",
}

const STATUS_BADGE: Record<string, { label: string; className: string; icon?: boolean; title?: string }> = {
  completed:       { label: "Completed",       className: "bg-success/10 text-success" },
  importing:       { label: "Importing…",      className: "bg-primary/10 text-primary animate-pulse" },
  throttled:       { label: "Throttled",       className: "bg-primary/10 text-warning" },
  daily_limit:     { label: "Daily Limit",     className: "bg-primary/10 text-destructive" },
  error:           { label: "Error",           className: "bg-destructive text-white shadow-sm flex items-center gap-1", icon: true, title: "Import failed. Click to retry or re-upload." },
  failed:          { label: "Failed",          className: "bg-destructive text-white shadow-sm flex items-center gap-1", icon: true, title: "Import failed. Click to retry or re-upload." },
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
  onRetryList?: (list: LeadList) => void
  onOpenSegmentation?: (list: LeadList) => void
}

export function LeadTable({
  lists,
  isLoading,
  error,
  mutate,
  onAddLeads,
  onSelectList,
  onDeleteList,
  onRetryList,
  onOpenSegmentation
}: LeadTableProps) {
    return (
      <AnimatePresence mode="wait">
        {error ? (
          <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }} className="mb-6 flex items-center justify-between p-3 rounded-lg border border-primary/20 bg-primary/10 text-warning">
            <div className="flex items-center gap-2 text-sm font-medium">
              <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              {"Backend connection lost. Retrying..."}
            </div>
            <button type="button" onClick={() => mutate()} className="text-xs font-bold hover:underline">Reconnect</button>
          </motion.div>
        ) : isLoading && lists.length === 0 ? (
          <motion.div key="skeleton" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}>
            <TableSkeleton rows={5} />
          </motion.div>
        ) : lists.length === 0 ? (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}>
            <div className="flex flex-col items-center justify-center py-20 border border-border/50 bg-card/40 backdrop-blur-sm text-center px-8 rounded-xl shadow-sm">
              <div className="w-14 h-14 rounded-lg border border-border/60 bg-muted/40 flex items-center justify-center mb-5">
                <Users size={22} className="text-primary" />
              </div>
              <h2 className="text-lg font-semibold tracking-tight text-foreground mb-2">
                No lead lists found
              </h2>
              <p className="text-xs text-muted-foreground leading-relaxed max-w-sm mb-4">
                Import contacts from a CSV file, paste LinkedIn URLs, or sync directly from Sales Navigator to begin outreach.
              </p>
              <a
                href="/template_leads.csv"
                download
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-6"
              >
                <Download size={12} /> Download CSV template
              </a>
              <button 
                type="button"
                onClick={onAddLeads}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary/90 rounded-lg text-xs font-bold text-primary-foreground transition-all shadow-sm"
              >
                <Plus size={14} /> Import a lead list
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div key="list" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}>
    <div className="space-y-2.5">
      <div className="flex items-center justify-between mb-3 mt-1">
        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
          {lists.length} {lists.length === 1 ? 'list' : 'lists'}
        </span>
      </div>
      <AnimatePresence>
      {lists.map((list, i) => (
        <motion.div
          key={list.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, x: -20, transition: { duration: 0.25 } }}
          transition={{ delay: i * 0.05 }}
        >
          <div 
            className="relative overflow-hidden flex items-center justify-between gap-4 px-4 sm:px-5 py-3.5 border border-border/50 bg-card/40 backdrop-blur-sm hover:border-border hover:bg-card/70 transition-all rounded-xl shadow-xs group" 
          >
            <div
              role="button"
              tabIndex={0}
              aria-label={`Open lead list ${list.name}`}
              onClick={() => onSelectList(list)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectList(list); } }}
              className="flex items-center gap-4 flex-1 min-w-0 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded-lg py-1"
            >
              <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${(() => {
                switch(list.type) {
                  case 'csv': return 'text-success bg-success/10 border-success/20';
                  case 'sales_nav': return 'text-primary bg-primary/10 border-primary/20';
                  case 'search': return 'text-primary bg-primary/10 border-primary/20';
                  case 'linkedin_url': return 'text-primary bg-primary/10 border-primary/20';
                  case 'hubspot': return 'text-primary bg-primary/10 border-primary/20';
                  case 'dynamic': return 'text-primary bg-primary/15 border-primary/30';
                  default: return 'text-primary bg-primary/10 border-primary/20';
                }
              })()}`}>
                {(() => {
                  if ((list as any).status === 'importing' || list.row_count === -1) return <div className="animate-pulse"><Users size={15} /></div>;
                  switch(list.type) {
                    case 'csv': return <FileSpreadsheet size={15} />;
                    case 'sales_nav': return <Compass size={15} />;
                    case 'search': return <Search size={15} />;
                    case 'linkedin_url': return <Link2 size={15} />;
                    case 'dynamic': return <Sliders size={15} />;
                    default: return <Users size={15} />;
                  }
                })()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-foreground truncate">{list.name}</p>
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
                <div className="flex items-center gap-2.5 mt-0.5">
                  <span className="text-[11px] font-medium text-muted-foreground">{TYPE_LABEL[list.type] || list.type}</span>
                  <span className="text-[11px] text-border">•</span>
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
                      if (st === 'error' || st === 'failed') return <span className="flex items-center gap-1.5 text-destructive"><AlertCircle size={11} /> {(list as any).error_message || "Import failed. Please retry."}</span>
                      if (st.startsWith('completed') && st.includes('duplicates')) return <span className="text-muted-foreground">{list.row_count.toLocaleString()} leads <span className="text-warning">· {st.split('—')[1]?.trim()}</span></span>
                      return `${list.row_count.toLocaleString()} leads`
                    })()}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 pr-1 relative z-10">
              {(() => {
                const st = (list as any).status || (list.row_count === -1 ? 'importing' : list.row_count === -2 ? 'error' : 'completed')
                if ((st === 'error' || st === 'failed' || st === 'session_expired' || st === 'throttled') && onRetryList) {
                  return (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRetryList(list);
                      }}
                      className="px-2.5 py-1 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/25 text-[11px] font-bold flex items-center gap-1 transition-all shadow-xs"
                      title="Retry or fix this import"
                    >
                      <RotateCw size={11} />
                      <span>Retry</span>
                    </button>
                  );
                }
                return null;
              })()}
              {onOpenSegmentation && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenSegmentation(list);
                  }}
                  className="px-2.5 py-1 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/25 text-[11px] font-semibold flex items-center gap-1 transition-all shadow-xs"
                  title="Configure Dynamic Rules & Auto-Enrollment"
                >
                  <Sliders size={11} />
                  <span>Dynamic Rules</span>
                </button>
              )}
              <span className="text-[11px] text-muted-foreground font-medium mr-1 hidden sm:inline">
                {new Date(list.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onDeleteList(list); }}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                title="Delete list"
              >
                <Trash2 size={15} />
              </button>
              <div className="w-4 flex items-center justify-center opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200">
                <ChevronRight size={16} className="text-muted-foreground" />
              </div>
            </div>
            
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
          </div>
        </motion.div>
      ))}
      </AnimatePresence>
      </div>
          </motion.div>
        )}
      </AnimatePresence>
    );
}
