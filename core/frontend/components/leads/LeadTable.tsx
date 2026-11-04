import { motion, AnimatePresence } from "motion/react"
import { Users, FileSpreadsheet, Compass, Search, Link2, Trash2, ChevronRight, AlertCircle, Plus, Download, RotateCw, Sliders, Send, Sparkles, Database, CheckCircle2 } from "lucide-react"
import { TableSkeleton } from "../EleInSkeleton"
import type { LeadList } from "./leads.types"
import { StatusPill } from "@/components/StatusPill"

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
  onEnrollList?: (list: LeadList) => void
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
  onOpenSegmentation,
  onEnrollList
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
            <div className="flex flex-col items-center justify-center py-12 md:py-16 border border-border/80 bg-card rounded-2xl shadow-xs px-6 max-w-4xl mx-auto">
              {/* Top Badge & Header */}
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-4 shadow-2xs">
                <Sparkles size={13} className="text-primary animate-pulse" />
                <span>Audience Intelligence Launchpad</span>
              </div>

              <h2 className="text-xl md:text-2xl font-bold tracking-tight text-foreground text-center mb-2">
                Build your high-intent prospect pipeline
              </h2>
              <p className="text-xs md:text-sm text-muted-foreground text-center max-w-lg mb-8 leading-relaxed">
                Import target accounts through your preferred channel. EleIn automatically validates vanity URLs, cleanses duplicates, and monitors profile health.
              </p>

              {/* 3 Interactive Ingestion Vector Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full mb-8">
                {/* Vector 1: CSV Upload */}
                <div className="p-5 rounded-xl border border-border bg-background/70 hover:border-primary/40 hover:bg-card/90 transition-all flex flex-col justify-between group text-left">
                  <div>
                    <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center mb-3.5 group-hover:scale-105 transition-transform">
                      <FileSpreadsheet size={20} className="text-primary" />
                    </div>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <h3 className="text-sm font-semibold text-foreground">CSV / Excel Upload</h3>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed mb-4">
                      Upload your spreadsheet with auto column-mapping for names, companies, and LinkedIn profiles.
                    </p>
                  </div>
                  <div className="space-y-2 pt-2 border-t border-border/60">
                    <button
                      type="button"
                      onClick={onAddLeads}
                      className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors cursor-pointer shadow-xs"
                    >
                      <Plus size={13} />
                      <span>Upload CSV</span>
                    </button>
                    <a
                      href="/template_leads.csv"
                      download
                      className="w-full flex items-center justify-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors py-1"
                    >
                      <Download size={11} />
                      <span>Download Template</span>
                    </a>
                  </div>
                </div>

                {/* Vector 2: Sales Navigator */}
                <div className="p-5 rounded-xl border border-border bg-background/70 hover:border-primary/40 hover:bg-card/90 transition-all flex flex-col justify-between group text-left">
                  <div>
                    <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center mb-3.5 group-hover:scale-105 transition-transform">
                      <Compass size={20} className="text-primary" />
                    </div>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <h3 className="text-sm font-semibold text-foreground">Sales Navigator Sync</h3>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed mb-4">
                      Paste saved search or account list URLs. Scrapes prospects with current titles and seniority levels.
                    </p>
                  </div>
                  <div className="pt-2 border-t border-border/60">
                    <button
                      type="button"
                      onClick={onAddLeads}
                      className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <Compass size={13} className="text-primary" />
                      <span>Sync Search URL</span>
                    </button>
                  </div>
                </div>

                {/* Vector 3: Direct LinkedIn URLs */}
                <div className="p-5 rounded-xl border border-border bg-background/70 hover:border-primary/40 hover:bg-card/90 transition-all flex flex-col justify-between group text-left">
                  <div>
                    <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center mb-3.5 group-hover:scale-105 transition-transform">
                      <Link2 size={20} className="text-primary" />
                    </div>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <h3 className="text-sm font-semibold text-foreground">LinkedIn URLs</h3>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed mb-4">
                      Paste a quick batch of LinkedIn vanity profile URLs for immediate waterfall discovery and verification.
                    </p>
                  </div>
                  <div className="pt-2 border-t border-border/60">
                    <button
                      type="button"
                      onClick={onAddLeads}
                      className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <Link2 size={13} className="text-primary" />
                      <span>Paste Profiles</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Rate Limit Protection Notice */}
              <div className="w-full p-3 rounded-xl border border-border/60 bg-muted/30 flex items-center gap-2.5 text-xs text-muted-foreground">
                <CheckCircle2 size={15} className="text-success shrink-0" />
                <span>
                  <strong className="text-foreground font-medium">Automatic Duplicate & Commercial Limit Filter:</strong> Leads enrolled across multiple lists are deduplicated so prospects never receive redundant touches.
                </span>
              </div>
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
          layout
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, x: -20, transition: { duration: 0.25 } }}
          transition={{ layout: { duration: 0.22, ease: [0.16, 1, 0.3, 1] }, delay: i * 0.04 }}
        >
          <div 
            className="relative overflow-hidden flex items-center justify-between gap-4 px-4 sm:px-5 py-3.5 border border-border/50 bg-card/40 backdrop-blur-sm hover:border-border hover:bg-card/70 transition-all rounded-xl shadow-xs group" 
          >
            <button
              type="button"
              aria-label={`Open lead list ${list.name}`}
              onClick={() => onSelectList(list)}
              className="text-left bg-transparent border-0 p-0 flex items-center gap-4 flex-1 min-w-0 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded-lg py-1"
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
                    if (st === 'completed') return null
                    return (
                      <StatusPill 
                        status={st === 'importing' ? 'verifying' : st === 'error' || st === 'failed' ? 'failed' : st === 'session_expired' ? 'disconnected' : st === 'throttled' ? 'rate_limited' : 'pending'} 
                        size="xs" 
                        label={st === 'importing' ? 'Importing...' : st === 'error' || st === 'failed' ? 'Error' : st === 'session_expired' ? 'Session Expired' : st === 'throttled' ? 'Throttled' : st}
                        pulse={st === 'importing'} 
                      />
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
                  {list.campaign && (
                    <>
                      <span className="text-[11px] text-border">•</span>
                      <span 
                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-md border border-emerald-500/20 shadow-xs"
                        title={typeof list.campaign === 'object' ? `Assigned to ${list.campaign.status || 'ACTIVE'} campaign: ${list.campaign.name}` : `Assigned to campaign: ${list.campaign}`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
                        <span className="truncate max-w-[140px] sm:max-w-[200px]">
                          Campaign: {typeof list.campaign === 'object' ? list.campaign.name : list.campaign}
                        </span>
                      </span>
                    </>
                  )}
                </div>
              </div>
            </button>
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
              {onEnrollList && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEnrollList(list);
                  }}
                  className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 text-[11px] font-semibold flex items-center gap-1 transition-all shadow-xs cursor-pointer"
                  title="Enroll this list into an automated outreach campaign"
                >
                  <Send size={11} />
                  <span>Enroll in Campaign</span>
                </button>
              )}
              <span className="text-[11px] text-muted-foreground font-medium mr-1 hidden sm:inline">
                {new Date(list.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
              <button
                type="button"
                aria-label={`Delete list ${list.name}`}
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
