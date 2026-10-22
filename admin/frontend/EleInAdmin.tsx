import { useState, useMemo, useEffect } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { friendlyToast } from "../../core/frontend/components/FriendlyError"
import { 
  LayoutTemplate, CheckCircle, CheckCircle2, XCircle, Clock, Key, Plus, 
  Trash2, RefreshCw, AlertCircle, AlertTriangle, Activity, Cpu, 
  ShieldCheck, ShieldAlert, Server, Zap, Database, Eye, X, Loader2, 
  Sparkles, Radio, Layers, ArrowRight
} from "lucide-react"

interface Template {
  id: string
  name: string
  description: string
  status: "private" | "pending" | "public" | "rejected"
  tags: string[]
  downloads: number
  created_at: string
  nodes?: any[]
  edges?: any[]
}

interface ApiKey {
  id: string
  provider: string
  api_key: string
  status: string
  error_count: number
  last_used_at: string
}

interface WorkerInfo {
  worker_id: string
  status: string
  raw_status?: string
  last_beat_at?: string
  is_alive: boolean
  last_tick_duration_ms?: number
  last_tick_leads_processed?: number
}

interface ProxyInfo {
  id: string
  host: string
  port: number
  status: string
  last_checked_at?: string
  provider?: string
}

export function EleInAdmin() {
  const [activeTab, setActiveTab] = useState<"infrastructure" | "keys" | "proxies" | "templates">("infrastructure")
  
  // ─── Template State ───
  const { data: pendingTemplates, mutate: mutateTemplates, isLoading: templatesLoading } = useSWR<Template[]>(
    '/api/assets/templates/admin/pending', 
    fetcher
  )
  const [loadingTemplateId, setLoadingTemplateId] = useState<string | null>(null)
  const [inspectingTemplate, setInspectingTemplate] = useState<Template | null>(null)

  // ─── API Key Pool State ───
  const { data: apiKeys, mutate: mutateKeys, isLoading: keysLoading } = useSWR<ApiKey[]>(
    '/api/settings/admin/api-keys', 
    fetcher
  )
  const [newKey, setNewKey] = useState("")
  const [isAddingKey, setIsAddingKey] = useState(false)
  const [deletingKeyId, setDeletingKeyId] = useState<string | null>(null)

  // ─── Worker Heartbeats State (Layer 0 & 1) ───
  const { data: workerData, mutate: mutateWorkers, isLoading: workersLoading } = useSWR<{
    status: string
    timestamp: string
    workers: WorkerInfo[]
  }>('/api/system/workers', fetcher, { refreshInterval: 10000 })

  // ─── Proxy Health State ───
  const { data: proxiesData, mutate: mutateProxies, isLoading: proxiesLoading } = useSWR<ProxyInfo[]>(
    '/api/elein/proxies/health', 
    fetcher, 
    { refreshInterval: 15000 }
  )

  // ─── Backend Liveness Ping Probe (Layer 1) ───
  const [probeLatencyMs, setProbeLatencyMs] = useState<number | null>(null)
  const [isProbing, setIsProbing] = useState<boolean>(false)

  const handleTestProbe = async () => {
    setIsProbing(true)
    const start = performance.now()
    try {
      const res = await fetchWithAuth('/api/system/health')
      const latency = Math.round(performance.now() - start)
      if (res.ok) {
        setProbeLatencyMs(latency)
        toast.success(`System Health Probe OK • ${latency}ms latency`)
      } else {
        setProbeLatencyMs(null)
        toast.error("System health probe returned non-200 status")
      }
    } catch {
      setProbeLatencyMs(null)
      toast.error("Failed to reach system health endpoint")
    } finally {
      setIsProbing(false)
    }
  }

  // Run probe once on mount
  useEffect(() => {
    handleTestProbe()
  }, [])

  // ─── Action Handlers: Templates ───
  const handleTemplateAction = async (id: string, action: "approve" | "reject") => {
    const template = safeTemplates.find(t => t.id === id)
    setLoadingTemplateId(id)
    try {
      const res = await fetchWithAuth(`/api/assets/templates/admin/${id}/${action}`, { method: "POST" })
      if (!res.ok) throw new Error(`Failed to ${action} template. Check if SUPABASE_SERVICE_KEY is configured.`)
      toast.success(`Template "${template?.name || 'Unknown'}" ${action}d successfully!`)
      mutateTemplates()
      if (inspectingTemplate?.id === id) setInspectingTemplate(null)
    } catch (e: any) {
      friendlyToast('Failed to update template status — please try again.', e)
    } finally {
      setLoadingTemplateId(null)
    }
  }

  // ─── Action Handlers: API Keys (Layer 0, 1 & 2) ───
  const handleAddKey = async () => {
    const k = newKey.trim()
    if (!k.startsWith("nvapi-") && !k.startsWith("sk-") && !k.startsWith("sk-ant-") && !k.startsWith("ollama") && !k.startsWith("lmstudio")) {
      toast.error("Invalid AI API Key format. Must start with nvapi-, sk-, sk-ant-, ollama-, or lmstudio-")
      return
    }
    setIsAddingKey(true)
    try {
      const res = await fetchWithAuth("/api/settings/admin/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: k })
      })
      if (!res.ok) {
        let err = "Failed to add key"
        try { const d = await res.json(); err = d.detail || err; } catch(_) {}
        throw new Error(err)
      }
      toast.success(`AI API key (${k.substring(0, 12)}...) added to pool!`)
      setNewKey("")
      mutateKeys()
    } catch (e: any) {
      friendlyToast('Failed to add API key — please try again.', e)
    } finally {
      setIsAddingKey(false)
    }
  }

  const handleDeleteKey = async (id: string) => {
    if (deletingKeyId === id) {
      const keyObj = safeKeys.find(k => k.id === id)
      try {
        await fetchWithAuth(`/api/settings/admin/api-keys/${id}`, { method: "DELETE" })
        toast.success(`Key (${keyObj?.api_key.substring(0, 12)}...) removed from pool`)
        setDeletingKeyId(null)
        mutateKeys()
      } catch {
        toast.error("Failed to delete key")
      }
    } else {
      setDeletingKeyId(id)
      toast.info("Click Delete again to confirm key removal")
      setTimeout(() => setDeletingKeyId(null), 4000)
    }
  }

  const handleResetKey = async (id: string) => {
    const keyObj = safeKeys.find(k => k.id === id)
    try {
      await fetchWithAuth(`/api/settings/admin/api-keys/${id}/reset`, { method: "PUT" })
      toast.success(`Key (${keyObj?.api_key.substring(0, 12)}...) status reset to active`)
      mutateKeys()
    } catch {
      toast.error("Failed to reset key")
    }
  }

  const handleResetAllKeys = async () => {
    const rateLimited = safeKeys.filter(k => k.status !== 'active')
    if (rateLimited.length === 0) {
      toast.info("All keys in the pool are already active.")
      return
    }
    let resetCount = 0
    for (const k of rateLimited) {
      try {
        const res = await fetchWithAuth(`/api/settings/admin/api-keys/${k.id}/reset`, { method: "PUT" })
        if (res.ok) resetCount++
      } catch (_) {}
    }
    toast.success(`Reset ${resetCount} key${resetCount === 1 ? '' : 's'} to active status`)
    mutateKeys()
  }

  // ─── Safe Arrays & Derived Rollups ───
  const safeTemplates = Array.isArray(pendingTemplates) ? pendingTemplates : []
  const safeKeys = Array.isArray(apiKeys) ? apiKeys : []
  const safeWorkers = Array.isArray(workerData?.workers) ? workerData.workers : []
  const safeProxies = Array.isArray(proxiesData) ? proxiesData : []

  // Vitals Calculation
  const activeWorkersCount = safeWorkers.filter(w => w.is_alive).length
  const staleWorkersCount = safeWorkers.filter(w => !w.is_alive).length
  const activeKeysCount = safeKeys.filter(k => k.status === 'active').length
  const activeProxiesCount = safeProxies.filter(p => p.status === 'active' || p.status === 'ok').length

  return (
    <div className="max-w-[1240px] mx-auto p-6 sm:p-8 font-sans">
      {/* ─── HEADER COMMAND DECK ────────────────────────────────────────────── */}
      <div className="mb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              SuperAdmin &amp; Infrastructure Telemetry
            </h1>
            <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
              Root Authority
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Monitor real-time worker daemons, proxy pool health, AI key failovers, and community sequence moderation.
          </p>
        </div>

        {/* Global Liveness Probe CTA */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleTestProbe}
            disabled={isProbing}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-card hover:bg-muted border border-border/60 text-xs font-semibold rounded-xl transition-colors shadow-xs cursor-pointer"
          >
            {isProbing ? <Loader2 size={13} className="animate-spin" /> : <Radio size={13} className="text-primary" />}
            <span>Ping Backend ({probeLatencyMs !== null ? `${probeLatencyMs}ms` : "Test"})</span>
          </button>
        </div>
      </div>

      {/* ─── SYSTEM VITAL STATISTICS RIBBON (Layer 0) ───────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-8">
        {/* Card 1: Worker Daemons */}
        <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Worker Daemons</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-bold text-foreground font-mono">
                {activeWorkersCount}/{Math.max(1, safeWorkers.length)}
              </span>
              <span className={`text-[10px] font-bold ${activeWorkersCount > 0 ? 'text-emerald-600' : 'text-amber-500'}`}>
                {activeWorkersCount > 0 ? 'Alive & Ticking' : 'Idle / Stalled'}
              </span>
            </div>
          </div>
          <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <Cpu size={18} />
          </div>
        </div>

        {/* Card 2: AI Key Pool */}
        <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">AI Provider Pool</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-bold text-foreground font-mono">{activeKeysCount}</span>
              <span className="text-[10px] text-primary font-bold">
                {safeKeys.length > activeKeysCount ? `(${safeKeys.length - activeKeysCount} limited)` : 'Ready'}
              </span>
            </div>
          </div>
          <div className="w-9 h-9 rounded-lg bg-purple-500/10 text-purple-600 flex items-center justify-center shrink-0">
            <Key size={18} />
          </div>
        </div>

        {/* Card 3: Residential Proxies */}
        <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Residential Proxies</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-bold text-foreground font-mono">
                {activeProxiesCount}/{Math.max(1, safeProxies.length)}
              </span>
              <span className="text-[10px] text-emerald-600 font-bold">Operational</span>
            </div>
          </div>
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 text-emerald-600 flex items-center justify-center shrink-0">
            <ShieldCheck size={18} />
          </div>
        </div>

        {/* Card 4: Template Review Queue */}
        <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Pending Playbooks</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-bold text-foreground font-mono">{safeTemplates.length}</span>
              <span className="text-[10px] text-muted-foreground">In Review</span>
            </div>
          </div>
          <div className="w-9 h-9 rounded-lg bg-amber-500/10 text-amber-600 flex items-center justify-center shrink-0">
            <Clock size={18} />
          </div>
        </div>
      </div>

      {/* ─── ENVIRONMENTAL ALERT BANNER (Layer 1) ───────────────────────────── */}
      {staleWorkersCount > 0 && (
        <div className="mb-6 p-4 rounded-xl border border-destructive/30 bg-destructive/10 flex items-start gap-3 shadow-xs">
          <AlertTriangle className="text-destructive shrink-0 mt-0.5" size={18} />
          <div>
            <h4 className="text-xs font-bold text-destructive">
              {staleWorkersCount} Background Worker Daemon{staleWorkersCount > 1 ? 's' : ''} Stalled or Stale
            </h4>
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
              Worker heartbeats have not been recorded within the last 120 seconds. Outbound LinkedIn actions, message queueing, or knowledge base scraping may be paused. If this persists, restart via <code className="bg-muted px-1.5 py-0.5 rounded text-foreground font-mono">./backend/start.sh</code>.
            </p>
          </div>
        </div>
      )}

      {/* ─── TABS NAVIGATION ────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 border-b border-border/60 pb-3 mb-6 overflow-x-auto">
        <button 
          onClick={() => setActiveTab("infrastructure")}
          className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
            activeTab === "infrastructure" 
              ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20" 
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <Cpu size={14} />
          <span>Worker Heartbeats & Infrastructure</span>
        </button>

        <button 
          onClick={() => setActiveTab("keys")}
          className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
            activeTab === "keys" 
              ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20" 
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <Key size={14} />
          <span>AI Key Pool ({safeKeys.length})</span>
        </button>

        <button 
          onClick={() => setActiveTab("proxies")}
          className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
            activeTab === "proxies" 
              ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20" 
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <ShieldCheck size={14} />
          <span>Proxy Health ({safeProxies.length})</span>
        </button>

        <button 
          onClick={() => setActiveTab("templates")}
          className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
            activeTab === "templates" 
              ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20" 
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <LayoutTemplate size={14} />
          <span>Community Playbooks ({safeTemplates.length})</span>
        </button>
      </div>

      {/* ─── TAB 1: INFRASTRUCTURE & WORKERS (Layer 0 & 1) ───────────────────── */}
      {activeTab === "infrastructure" && (
        <div className="space-y-6">
          <div className="p-6 rounded-xl border border-border/60 bg-card shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-border/50">
              <div>
                <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                  <Activity size={18} className="text-primary" />
                  Live Daemon Pulse & Queue Heartbeats
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Real-time telemetry reported from asynchronous engine workers and outbox orchestrators.
                </p>
              </div>

              <button
                onClick={() => mutateWorkers()}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-muted hover:bg-muted/80 rounded-xl text-xs font-semibold text-foreground transition-all cursor-pointer self-start sm:self-auto"
              >
                <RefreshCw size={12} />
                <span>Refresh Pulse</span>
              </button>
            </div>

            {safeWorkers.length > 0 ? (
              <div className="divide-y divide-border/60">
                {safeWorkers.map(w => {
                  const isAlive = w.is_alive
                  const beatDate = w.last_beat_at ? new Date(w.last_beat_at).toLocaleTimeString() : "Never"

                  return (
                    <div key={w.worker_id} className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-3 h-3 rounded-full ${isAlive ? 'bg-success animate-pulse shadow-[0_0_8px_var(--success)]' : 'bg-destructive'}`} />
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-bold text-foreground font-mono">{w.worker_id}</h4>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full capitalize ${
                              isAlive ? 'bg-success/10 text-success border border-success/20' : 'bg-destructive/10 text-destructive border border-destructive/20'
                            }`}>
                              {w.status}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Last beat: <span className="font-semibold text-foreground">{beatDate}</span>
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground bg-muted/30 px-3 py-2 rounded-xl border border-border/40">
                        <div>
                          <span className="text-[10px] text-muted-foreground block uppercase">Tick Duration</span>
                          <span className="font-bold text-foreground">{w.last_tick_duration_ms ?? 0}ms</span>
                        </div>
                        <div className="h-6 w-px bg-border/60" />
                        <div>
                          <span className="text-[10px] text-muted-foreground block uppercase">Leads Processed</span>
                          <span className="font-bold text-primary">{w.last_tick_leads_processed ?? 0}</span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="py-12 text-center flex flex-col items-center">
                <Server size={32} className="text-muted-foreground/40 mb-3" />
                <h4 className="text-sm font-bold text-foreground mb-1">No Active Worker Beacons Detected</h4>
                <p className="text-xs text-muted-foreground max-w-sm mb-4">
                  Workers report liveness when executing campaigns. Ensure background services are running via ./backend/start.sh.
                </p>
                <button
                  onClick={() => mutateWorkers()}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-bold"
                >
                  Poll Workers Now
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── TAB 2: AI KEY POOL & FAILOVER ENGINE ───────────────────────────── */}
      {activeTab === "keys" && (
        <div className="space-y-6">
          <div className="p-6 rounded-xl border border-border/60 bg-card shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold flex items-center gap-2 text-foreground">
                <Key size={16} className="text-primary" /> 
                Add AI Provider Key to High-Availability Pool
              </h3>
              <button
                type="button"
                onClick={handleResetAllKeys}
                className="text-xs font-semibold text-primary hover:underline cursor-pointer flex items-center gap-1"
              >
                <RefreshCw size={12} />
                <span>Reset All Limited Keys</span>
              </button>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <input 
                type="password"
                placeholder="nvapi-..., sk-..., sk-ant-..., ollama-..., lmstudio-..."
                value={newKey}
                onChange={e => setNewKey(e.target.value)}
                className="flex-1 bg-background border border-border/60 rounded-xl px-4 py-2.5 text-xs font-mono text-foreground focus:outline-none focus:border-primary focus:ring-1 ring-primary"
              />
              <button 
                type="button"
                onClick={handleAddKey}
                disabled={isAddingKey || !newKey.trim()}
                className="flex items-center justify-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground font-bold text-xs rounded-xl hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer whitespace-nowrap shadow-xs"
              >
                {isAddingKey ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                <span>Add Key to Pool</span>
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
              Keys are pooled across providers. If a key encounters rate limits or token exhaustion during sequence personalization, the orchestrator instantly fails over to the next available healthy key.
            </p>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-foreground">Active Pool Distribution ({safeKeys.length})</h3>
              <span className="text-xs text-muted-foreground">{activeKeysCount} operational</span>
            </div>

            {safeKeys.map(k => (
              <div key={k.id} className="flex items-center justify-between p-4 rounded-xl border border-border/60 bg-card group shadow-xs">
                <div className="flex items-center gap-3.5">
                  <div className={`w-2.5 h-2.5 rounded-full ${
                    k.status === 'active' 
                      ? 'bg-success shadow-[0_0_8px_var(--success)]' 
                      : k.status === 'rate_limited' 
                      ? 'bg-warning' 
                      : 'bg-destructive'
                  }`} />
                  <div>
                    <p className="text-xs font-mono font-bold text-foreground">{k.api_key}</p>
                    <p className="text-[11px] text-muted-foreground capitalize mt-0.5">
                      Status: <span className="font-semibold text-foreground">{k.status.replace("_", " ")}</span> • {k.error_count} error{k.error_count === 1 ? '' : 's'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {k.status !== 'active' && (
                    <button 
                      onClick={() => handleResetKey(k.id)}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-success hover:bg-success/10 rounded-lg transition-colors cursor-pointer"
                      title="Reset Status to Active"
                    >
                      <RefreshCw size={12} />
                      <span>Reset</span>
                    </button>
                  )}
                  <button 
                    onClick={() => handleDeleteKey(k.id)}
                    className={`p-2 rounded-lg transition-colors cursor-pointer ${
                      deletingKeyId === k.id 
                        ? 'bg-destructive text-destructive-foreground' 
                        : 'text-muted-foreground hover:text-destructive hover:bg-destructive/10'
                    }`}
                    title={deletingKeyId === k.id ? "Click to confirm deletion" : "Remove from pool"}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}

            {safeKeys.length === 0 && (
              <div className="py-12 text-center flex flex-col items-center bg-card rounded-xl border border-dashed border-border/60">
                <AlertCircle size={24} className="text-muted-foreground/50 mb-2" />
                <h4 className="text-sm font-bold text-foreground mb-1">AI Key Pool is Empty</h4>
                <p className="text-xs text-muted-foreground max-w-sm mb-3">
                  Add an OpenAI, Anthropic, or NVIDIA NIM API key above to empower autonomous copywriting and objection handling.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── TAB 3: PROXY HEALTH & LATENCIES ─────────────────────────────────── */}
      {activeTab === "proxies" && (
        <div className="space-y-6">
          <div className="p-6 rounded-xl border border-border/60 bg-card shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-border/50">
              <div>
                <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                  <ShieldCheck size={18} className="text-emerald-600" />
                  Residential Proxy Pool Fleet
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Static and residential IPs allocated to prevent LinkedIn geolocation mismatch checkpoints.
                </p>
              </div>

              <button
                onClick={() => mutateProxies()}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-muted hover:bg-muted/80 rounded-xl text-xs font-semibold text-foreground transition-all cursor-pointer self-start sm:self-auto"
              >
                <RefreshCw size={12} />
                <span>Re-Check Proxies</span>
              </button>
            </div>

            {safeProxies.length > 0 ? (
              <div className="divide-y divide-border/60">
                {safeProxies.map(p => {
                  const isOk = p.status === 'active' || p.status === 'ok'
                  return (
                    <div key={p.id} className="py-3.5 flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-2.5 h-2.5 rounded-full ${isOk ? 'bg-success shadow-[0_0_8px_var(--success)]' : 'bg-destructive'}`} />
                        <div>
                          <p className="text-xs font-mono font-bold text-foreground">{p.host}:{p.port}</p>
                          <p className="text-[11px] text-muted-foreground mt-0.5">
                            Provider: <span className="font-semibold text-foreground">{p.provider || "Webshare / Residential"}</span>
                          </p>
                        </div>
                      </div>

                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full capitalize ${
                        isOk ? 'bg-success/10 text-success border border-success/20' : 'bg-destructive/10 text-destructive border border-destructive/20'
                      }`}>
                        {p.status}
                      </span>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="py-12 text-center flex flex-col items-center">
                <ShieldCheck size={32} className="text-muted-foreground/40 mb-3" />
                <h4 className="text-sm font-bold text-foreground mb-1">No Dedicated Proxies Configured</h4>
                <p className="text-xs text-muted-foreground max-w-sm mb-4">
                  Outreach accounts are operating via direct residential proxy bindings or sandbox gateways.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── TAB 4: COMMUNITY PLAYBOOK REVIEW ───────────────────────────────── */}
      {activeTab === "templates" && (
        <div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {safeTemplates.map((tpl, i) => (
              <motion.div
                key={tpl.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
              >
                <div className="h-full flex flex-col p-6 rounded-xl border border-border/60 bg-card shadow-xs hover:border-primary/40 transition-all">
                  <div className="flex justify-between items-start mb-4">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                      <LayoutTemplate size={18} />
                    </div>
                    <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 text-[10px] font-bold border border-amber-500/20">
                      <Clock size={11} /> Pending Review
                    </span>
                  </div>
                  
                  <h3 className="text-base font-bold text-foreground tracking-tight mb-2">
                    {tpl.name}
                  </h3>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-6 flex-1 line-clamp-3">
                    {tpl.description || "Community sequence submitted for global distribution."}
                  </p>

                  <div className="flex items-center gap-2 pt-4 border-t border-border/50 mt-auto">
                    <button 
                      type="button"
                      onClick={() => setInspectingTemplate(tpl)}
                      className="px-3 py-2 bg-muted hover:bg-muted/80 rounded-xl text-xs font-semibold text-foreground transition-all cursor-pointer"
                    >
                      <Eye size={13} />
                    </button>
                    <button 
                      type="button"
                      onClick={() => handleTemplateAction(tpl.id, "approve")}
                      disabled={loadingTemplateId === tpl.id}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-success text-white rounded-xl text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
                    >
                      {loadingTemplateId === tpl.id ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
                      <span>Approve</span>
                    </button>
                    <button 
                      type="button"
                      onClick={() => handleTemplateAction(tpl.id, "reject")}
                      disabled={loadingTemplateId === tpl.id}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-destructive/10 hover:bg-destructive/20 border border-destructive/20 text-destructive rounded-xl text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      <XCircle size={13} />
                      <span>Reject</span>
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}

            {safeTemplates.length === 0 && (
              <div className="col-span-full py-16 text-center flex flex-col items-center justify-center rounded-xl border border-dashed border-border/60 bg-card p-8">
                <CheckCircle2 size={36} className="text-emerald-500/60 mb-3" />
                <h3 className="text-sm font-bold text-foreground mb-1">Curation Queue Empty</h3>
                <p className="text-xs text-muted-foreground max-w-sm">
                  All community sequence templates have been audited and resolved.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── TEMPLATE INSPECT DRAWER / MODAL ─────────────────────────────────── */}
      <AnimatePresence>
        {inspectingTemplate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg bg-card rounded-xl shadow-2xl border border-border p-6 flex flex-col max-h-[85vh] overflow-hidden"
            >
              <div className="flex items-start justify-between pb-4 border-b border-border/60 mb-4">
                <div>
                  <h3 className="text-base font-bold text-foreground">{inspectingTemplate.name}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{inspectingTemplate.description}</p>
                </div>
                <button onClick={() => setInspectingTemplate(null)} className="text-muted-foreground hover:text-foreground">
                  <X size={16} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto space-y-3 mb-5">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Sequence Steps</h4>
                {inspectingTemplate.nodes && inspectingTemplate.nodes.length > 0 ? (
                  inspectingTemplate.nodes.map((node, idx) => (
                    <div key={idx} className="p-3 bg-muted/40 rounded-xl border border-border/40 text-xs">
                      <div className="font-bold text-foreground capitalize">{node.type?.replace(/_/g, " ")}</div>
                      {node.data?.body && (
                        <p className="text-muted-foreground font-mono mt-1 text-[11px] line-clamp-3">{node.data.body}</p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">No sequence nodes found in payload.</p>
                )}
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/60">
                <button
                  onClick={() => handleTemplateAction(inspectingTemplate.id, "reject")}
                  className="px-4 py-2 bg-destructive/10 text-destructive text-xs font-bold rounded-xl"
                >
                  Reject
                </button>
                <button
                  onClick={() => handleTemplateAction(inspectingTemplate.id, "approve")}
                  className="px-4 py-2 bg-success text-white text-xs font-bold rounded-xl"
                >
                  Approve to Public Hub
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}
