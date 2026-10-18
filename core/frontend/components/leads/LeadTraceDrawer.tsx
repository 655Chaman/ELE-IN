import React, { useState, useEffect } from "react"
import { motion } from "motion/react"
import useSWR from "swr"
import { 
  X, Network, BrainCircuit, Clock, AlertCircle, CheckCircle2, 
  Download, Copy, Check, RefreshCw, Filter, ShieldCheck, Zap
} from "lucide-react"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { formatDistanceToNow } from "date-fns"
import { toast } from "sonner"
import { ElesiumLogo } from "@/components/ElesiumLogo"

export function LeadTraceDrawer({ 
  campaignId, 
  enrollmentId, 
  leadName, 
  onClose 
}: { 
  campaignId: string; 
  enrollmentId: string; 
  leadName: string;
  onClose: () => void;
}) {
  const { data: traces, isLoading, error, mutate } = useSWR(
    `/api/elein/campaigns/${campaignId}/enrollments/${enrollmentId}/trace`, 
    fetcher
  )

  const [filterStatus, setFilterStatus] = useState<"ALL" | "SUCCESS" | "FAILED" | "PENDING">("ALL")
  const [copiedTrace, setCopiedTrace] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)

  // Escape key dismiss
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onClose])

  const rawTraces: any[] = Array.isArray(traces) ? traces : []

  const filteredTraces = rawTraces.filter((t: any) => {
    if (filterStatus === "ALL") return true
    if (filterStatus === "SUCCESS") return t.status === "success"
    if (filterStatus === "FAILED") return t.status === "failed" || t.status === "error"
    if (filterStatus === "PENDING") return t.status === "pending" || t.status === "running"
    return true
  })

  const hasFailedNodes = rawTraces.some((t: any) => t.status === "failed" || t.status === "error")

  const handleExportJson = () => {
    if (rawTraces.length === 0) {
      toast.error("No execution trace data available to export.")
      return
    }
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(rawTraces, null, 2))
    const downloadAnchor = document.createElement("a")
    downloadAnchor.setAttribute("href", dataStr)
    downloadAnchor.setAttribute("download", `trace_${enrollmentId}_${new Date().toISOString().slice(0, 10)}.json`)
    document.body.appendChild(downloadAnchor)
    downloadAnchor.click()
    downloadAnchor.remove()
    toast.success("Exported execution trace JSON.")
  }

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(rawTraces, null, 2))
    setCopiedTrace(true)
    toast.success("Copied execution trace to clipboard!")
    setTimeout(() => setCopiedTrace(false), 2000)
  }

  const handleRetryFailed = async () => {
    setIsRetrying(true)
    try {
      const res = await fetchWithAuth(`/api/elein/campaigns/${campaignId}/enrollments/${enrollmentId}/retry-failed-node`, {
        method: "POST"
      })
      if (res.ok) {
        toast.success("Queued failed nodes for retry execution!")
        mutate()
      } else {
        toast.error("Failed to trigger node retry.")
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error retrying node.")
    } finally {
      setIsRetrying(false)
    }
  }

  return (
    <div 
      className="fixed inset-0 z-[70] flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby="lead-trace-title"
    >
      <motion.div 
        initial={{ opacity: 0 }} 
        animate={{ opacity: 1 }} 
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-background/80 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div 
        initial={{ x: "100%" }} 
        animate={{ x: 0 }} 
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className="relative w-full max-w-xl bg-card border-l border-border h-full flex flex-col shadow-2xl"
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-border bg-muted/40">
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Network size={16} />
              </div>
              <h2 id="lead-trace-title" className="text-base font-bold text-foreground">
                Autonomous Execution Trace
              </h2>
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary border border-primary/20">
                DAG Telemetry
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1 font-medium">
              Lead: <span className="text-foreground font-semibold">{leadName}</span> • Enrollment: <span className="font-mono text-[11px]">{enrollmentId.slice(0, 12)}</span>
            </p>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleCopyJson}
              title="Copy Trace JSON"
              aria-label="Copy trace JSON"
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              {copiedTrace ? <Check size={16} className="text-emerald-600 dark:text-emerald-400" /> : <Copy size={16} />}
            </button>
            <button
              onClick={handleExportJson}
              title="Download Trace JSON"
              aria-label="Download trace JSON"
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <Download size={16} />
            </button>
            <button 
              onClick={onClose} 
              aria-label="Close execution trace drawer"
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer ml-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Action & Filter Bar */}
        <div className="flex items-center justify-between px-6 py-2.5 border-b border-border/60 bg-muted/20 text-xs">
          <div className="flex items-center gap-1">
            <Filter size={13} className="text-muted-foreground mr-1" />
            {(["ALL", "SUCCESS", "PENDING", "FAILED"] as const).map(status => (
              <button
                key={status}
                onClick={() => setFilterStatus(status)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  filterStatus === status 
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                {status}
              </button>
            ))}
          </div>

          {hasFailedNodes && (
            <button
              onClick={handleRetryFailed}
              disabled={isRetrying}
              className="flex items-center gap-1.5 rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30 px-2.5 py-1 text-xs font-semibold hover:bg-amber-500/30 transition-all cursor-pointer disabled:opacity-50"
            >
              <RefreshCw size={12} className={isRetrying ? "animate-spin" : ""} />
              <span>Retry Failed Node</span>
            </button>
          )}
        </div>

        {/* Trace Stream Container */}
        <div className="flex-1 overflow-y-auto p-6 bg-background">
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="h-24 rounded-xl bg-muted/40 animate-pulse border border-border/50" />
              ))}
            </div>
          ) : error ? (
            <div className="p-6 text-center text-destructive bg-destructive/10 rounded-xl border border-destructive/20 text-sm space-y-2">
              <AlertCircle size={24} className="mx-auto" />
              <div className="font-semibold">Failed to load execution trace.</div>
              <p className="text-xs text-muted-foreground">The trace service encountered an error or network timeout.</p>
              <button 
                onClick={() => mutate()} 
                className="mt-2 text-xs font-semibold underline cursor-pointer"
              >
                Retry Request
              </button>
            </div>
          ) : filteredTraces.length === 0 ? (
            <div className="py-20 flex flex-col items-center justify-center text-muted-foreground border-2 border-dashed border-border/50 rounded-xl bg-muted/10">
              <Network size={32} className="opacity-30 mb-3" />
              <p className="text-sm font-semibold text-foreground">No execution events found</p>
              <p className="text-xs text-muted-foreground mt-1">This lead has not triggered any nodes matching the filter.</p>
            </div>
          ) : (
            <div className="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-primary/30 before:via-border before:to-transparent">
              {filteredTraces.map((trace: any) => {
                const isSuccess = trace.status === "success"
                const isError = trace.status === "failed" || trace.status === "error"
                const isPending = trace.status === "pending" || trace.status === "running"
                const payload = trace.output_payload || {}
                const hasReasoning = !!payload.ai_reasoning
                
                return (
                  <div key={trace.id} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group">
                    {/* Status Node Icon */}
                    <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-background bg-card shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 shadow-sm">
                      {isSuccess ? (
                        <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400" />
                      ) : isError ? (
                        <AlertCircle size={16} className="text-destructive" />
                      ) : (
                        <Clock size={16} className="text-amber-600 dark:text-amber-400 animate-pulse" />
                      )}
                    </div>
                    
                    {/* Step Card */}
                    <div className="w-[calc(100%-3rem)] md:w-[calc(50%-2rem)] p-4 rounded-xl border border-border bg-card shadow-sm hover:shadow-md transition-shadow relative">
                      <div className="flex justify-between items-start mb-2 gap-2">
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${
                          isSuccess
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                            : isError
                            ? "bg-destructive/10 text-destructive border-destructive/20"
                            : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
                        }`}>
                          {trace.node_type?.replace(/_/g, ' ') || "Action"}
                        </span>
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                          {trace.created_at ? formatDistanceToNow(new Date(trace.created_at), { addSuffix: true }) : "recently"}
                        </span>
                      </div>
                      
                      {payload.branch && (
                        <p className="text-xs font-medium text-foreground mb-1">
                          Branched to: <span className="text-primary font-semibold">"{payload.branch}"</span>
                        </p>
                      )}

                      {payload.channel && (
                        <p className="text-xs text-muted-foreground">
                          Channel: <span className="font-semibold text-foreground uppercase">{payload.channel}</span>
                        </p>
                      )}
                      
                      {isError && (
                        <div className="text-xs text-destructive mt-2 bg-destructive/10 p-2.5 rounded-lg border border-destructive/20 space-y-1">
                          <div className="font-semibold flex items-center gap-1">
                            <AlertCircle size={13} />
                            Execution Fault
                          </div>
                          <p className="font-mono text-[11px]">
                            {trace.error_code || payload.error || "Unknown execution failure"}
                          </p>
                        </div>
                      )}
                      
                      {hasReasoning && (
                        <div className="mt-2.5 p-2.5 bg-primary/5 border border-primary/20 rounded-lg">
                          <div className="flex items-center gap-1.5 mb-1 text-primary">
                            <ElesiumLogo size={13} />
                            <span className="text-[10px] font-bold uppercase tracking-wider">AI Reasoning</span>
                          </div>
                          <p className="text-xs text-foreground/90 italic leading-relaxed">
                            "{payload.ai_reasoning}"
                          </p>
                        </div>
                      )}

                      {payload.condition && (
                        <div className="mt-2 text-[11px] text-muted-foreground bg-muted/40 p-2 rounded border border-border/60">
                          Condition Gate: <span className="font-mono text-foreground">{payload.condition}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Drawer Footer */}
        <div className="px-6 py-3 border-t border-border bg-muted/30 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <ShieldCheck size={14} className="text-emerald-600 dark:text-emerald-400" />
            <span>Cryptographically sealed execution log</span>
          </div>
          <span className="font-mono text-[11px]">Nodes: {rawTraces.length}</span>
        </div>
      </motion.div>
    </div>
  )
}
