import React, { useState } from 'react'
import useSWR from 'swr'
import { motion, AnimatePresence } from 'motion/react'
import {
  X, Shield, ShieldCheck, AlertTriangle, RefreshCw, Plus, CheckCircle2,
  Zap, Globe, Server, Check, ArrowRight, Activity
} from 'lucide-react'
import { toast } from 'sonner'
import { fetcher, fetchWithAuth } from '@/lib/apiClient'
import { cn } from '@/lib/utils'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface ProxyItem {
  id: string
  provider: string
  host: string
  port: number
  protocol: string
  username?: string
  status: string
  country_code?: string
  latency_ms?: number
  exit_ip?: string
  last_checked_at?: string
  quarantined_until?: string
  quarantine_reason?: string
}

interface ProxyPoolStudioModalProps {
  onClose: () => void
}

export function ProxyPoolStudioModal({ onClose }: ProxyPoolStudioModalProps) {
  const { data: proxies, mutate, isLoading } = useSWR<ProxyItem[]>('/api/proxies', fetcher)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [isTestingAll, setIsTestingAll] = useState(false)
  const [isSyncingWebshare, setIsSyncingWebshare] = useState(false)
  const [showAddForm, setShowAddForm] = useState(false)

  // Layer 2 Paranoia: Close on Escape key
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  // Add Proxy Form State
  const [host, setHost] = useState('')
  const [port, setPort] = useState(8080)
  const [protocol, setProtocol] = useState('http')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [provider, setProvider] = useState('custom')
  const [isPreflightTesting, setIsPreflightTesting] = useState(false)
  const [preflightResult, setPreflightResult] = useState<{ ok: boolean; latency_ms: number; exit_ip?: string; error?: string } | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // 1-Click Ping a Single Proxy
  const handleTestProxy = async (id: string) => {
    setTestingId(id)
    try {
      const res = await fetchWithAuth(`/api/proxies/${id}/test`, { method: 'POST' })
      const data = await res.json()
      if (res.ok && data.ok) {
        toast.success(`Proxy Verified: ${data.latency_ms}ms latency`, {
          description: `Exit IP: ${data.exit_ip || 'Hidden'}`
        })
      } else {
        toast.error(`Proxy Failed: ${data.error || 'Connection timed out'}`)
      }
      mutate()
    } catch (e: any) {
      toast.error(e.message || 'Failed to ping proxy')
    } finally {
      setTestingId(null)
    }
  }

  // Batch Test All Proxies
  const handleTestAll = async () => {
    if (!proxies || proxies.length === 0) return
    setIsTestingAll(true)
    let passed = 0
    let failed = 0

    for (const p of proxies) {
      try {
        const res = await fetchWithAuth(`/api/proxies/${p.id}/test`, { method: 'POST' })
        const data = await res.json()
        if (res.ok && data.ok) passed++
        else failed++
      } catch {
        failed++
      }
    }

    setIsTestingAll(false)
    mutate()
    toast.info(`Proxy Pool Diagnostic Completed: ${passed} healthy, ${failed} degraded`)
  }

  // Sync Webshare Proxies
  const handleSyncWebshare = async () => {
    setIsSyncingWebshare(true)
    try {
      const res = await fetchWithAuth('/api/proxies/sync/webshare', { method: 'POST' })
      const data = await res.json()
      if (res.ok) {
        toast.success(`Webshare synced: ${data.synced || data.message || 'Pool updated'}`)
        mutate()
      } else {
        toast.error(data.detail || 'Failed to sync Webshare proxies')
      }
    } catch (e: any) {
      toast.error(e.message || 'Webshare sync failed')
    } finally {
      setIsSyncingWebshare(false)
    }
  }

  // Pre-flight Test Raw Config Before Saving
  const handlePreflightTest = async () => {
    if (!host.trim()) {
      toast.error('Host is required')
      return
    }
    setIsPreflightTesting(true)
    setPreflightResult(null)
    try {
      const res = await fetchWithAuth('/api/proxies/test-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: host.trim(), port: Number(port), protocol, username: username.trim() || undefined, password: password || undefined, provider })
      })
      const data = await res.json()
      setPreflightResult(data)
      if (res.ok && data.ok) {
        toast.success(`Pre-flight Passed: ${data.latency_ms}ms ping!`)
      } else {
        toast.error(`Pre-flight Failed: ${data.error || 'Connection refused'}`)
      }
    } catch (e: any) {
      setPreflightResult({ ok: false, latency_ms: 5000, error: e.message || 'Test failed' })
    } finally {
      setIsPreflightTesting(false)
    }
  }

  // Save New Proxy
  const handleCreateProxy = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!host.trim()) return
    setIsSubmitting(true)
    try {
      const res = await fetchWithAuth('/api/proxies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          host: host.trim(),
          port: Number(port),
          protocol,
          username: username.trim() || undefined,
          password: password || undefined
        })
      })
      if (res.ok) {
        toast.success('Residential proxy added to pool')
        setShowAddForm(false)
        setHost('')
        setUsername('')
        setPassword('')
        setPreflightResult(null)
        mutate()
      } else {
        const err = await res.json()
        toast.error(err.detail || 'Failed to add proxy')
      }
    } catch (e: any) {
      toast.error(e.message || 'Error saving proxy')
    } finally {
      setIsSubmitting(false)
    }
  }

  const safeProxies = Array.isArray(proxies) ? proxies : []
  const healthyCount = safeProxies.filter(p => p.status === 'healthy').length
  const latencies = safeProxies.map(p => p.latency_ms).filter((l): l is number => typeof l === 'number' && l > 0)
  const avgLatency = latencies.length > 0 ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="proxy-studio-title"
      onClick={onClose}
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-in fade-in duration-200"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-3xl rounded-xl bg-card border border-border shadow-2xl overflow-hidden flex flex-col max-h-[88vh] text-foreground"
      >
        {/* Modal Header */}
        <div className="p-6 border-b border-border flex items-center justify-between bg-muted/20 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center shrink-0">
              <ShieldCheck size={22} />
            </div>
            <div>
              <h2 id="proxy-studio-title" className="text-lg font-bold text-foreground flex items-center gap-2 flex-wrap">
                <span>Residential Proxy Pool & Latency Studio</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                  {healthyCount}/{safeProxies.length} Operational
                </span>
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Dedicated residential IP bindings keep your LinkedIn outreach safe with zero datacenter footprint.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        {/* Vital Metrics Bar */}
        <div className="px-6 py-3 border-b border-border/60 bg-muted/10 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs shrink-0">
          <div className="flex items-center gap-2">
            <Globe size={14} className="text-muted-foreground shrink-0" />
            <span className="text-muted-foreground">Total Proxies:</span>
            <strong className="text-foreground font-mono">{safeProxies.length}</strong>
          </div>
          <div className="flex items-center gap-2">
            <Activity size={14} className={avgLatency && avgLatency < 300 ? "text-emerald-600 dark:text-emerald-400 shrink-0" : "text-amber-500 shrink-0"} />
            <span className="text-muted-foreground">Avg Latency:</span>
            <strong className="text-foreground font-mono">{avgLatency ? `${avgLatency}ms` : '—'}</strong>
          </div>
          <div className="flex items-center justify-start sm:justify-end gap-2">
            <button
              type="button"
              onClick={handleTestAll}
              disabled={isTestingAll || safeProxies.length === 0}
              className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1 disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw size={11} className={isTestingAll ? "animate-spin" : ""} />
              <span>{isTestingAll ? "Pinging Pool..." : "Test All Proxies"}</span>
            </button>
            <span className="text-muted-foreground/40">·</span>
            <button
              type="button"
              onClick={handleSyncWebshare}
              disabled={isSyncingWebshare}
              className="text-[11px] font-semibold text-muted-foreground hover:text-foreground flex items-center gap-1 disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw size={11} className={isSyncingWebshare ? "animate-spin" : ""} />
              <span>{isSyncingWebshare ? "Syncing..." : "Sync Webshare"}</span>
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {/* Add Proxy Toggle Button */}
          {!showAddForm && (
            <div className="flex justify-between items-center">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Configured Proxies</span>
              <button
                type="button"
                onClick={() => setShowAddForm(true)}
                className="px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 border border-border text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <Plus size={13} />
                <span>Add Custom Proxy</span>
              </button>
            </div>
          )}

          {/* Add Proxy Inline Form */}
          <AnimatePresence>
            {showAddForm && (
              <motion.form
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                onSubmit={handleCreateProxy}
                className="p-5 rounded-lg bg-muted/30 border border-border space-y-4"
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                    <Server size={14} className="text-primary" />
                    <span>Add Dedicated Residential Proxy</span>
                  </h4>
                  <button
                    type="button"
                    onClick={() => { setShowAddForm(false); setPreflightResult(null) }}
                    className="text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="col-span-2 space-y-1">
                    <label className="text-muted-foreground font-medium">Host / IP *</label>
                    <input
                      value={host}
                      onChange={e => setHost(e.target.value)}
                      placeholder="e.g. 192.168.1.1 or proxy.residential.io"
                      required
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 text-xs font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-muted-foreground font-medium">Port *</label>
                    <input
                      type="number"
                      value={port}
                      onChange={e => setPort(Number(e.target.value))}
                      required
                      min={1}
                      max={65535}
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 text-xs font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-muted-foreground font-medium">Protocol</label>
                    <Select
                      value={protocol}
                      onValueChange={val => setProtocol(val)}
                    >
                      <SelectTrigger className="w-full h-8 px-3 py-2 rounded-md bg-background border-border text-foreground text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="http">HTTP</SelectItem>
                        <SelectItem value="https">HTTPS</SelectItem>
                        <SelectItem value="socks5">SOCKS5</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-muted-foreground font-medium">Username (Optional)</label>
                    <input
                      value={username}
                      onChange={e => setUsername(e.target.value)}
                      placeholder="user123"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 text-xs font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-muted-foreground font-medium">Password (Optional)</label>
                    <input
                      type="password"
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 text-xs font-mono"
                    />
                  </div>

                  <div className="col-span-2 space-y-1">
                    <label className="text-muted-foreground font-medium">Provider Label</label>
                    <input
                      value={provider}
                      onChange={e => setProvider(e.target.value)}
                      placeholder="e.g. BrightData, Webshare, Oxylabs"
                      className="w-full px-3 py-2 rounded-md bg-background border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 text-xs"
                    />
                  </div>
                </div>

                {/* Pre-flight Diagnostic Feedback */}
                {preflightResult && (
                  <div className={cn(
                    "p-3 rounded-md border text-xs flex items-center gap-2.5",
                    preflightResult.ok ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-300" : "bg-destructive/10 border-destructive/30 text-rose-600 dark:text-rose-300"
                  )}>
                    {preflightResult.ok ? <CheckCircle2 size={16} className="shrink-0 text-emerald-500 dark:text-emerald-400" /> : <AlertTriangle size={16} className="shrink-0 text-rose-500 dark:text-rose-400" />}
                    <div className="flex-1">
                      <span className="font-bold">{preflightResult.ok ? 'Connection Verified: ' : 'Test Failed: '}</span>
                      <span>{preflightResult.ok ? `${preflightResult.latency_ms}ms ping time (Exit IP: ${preflightResult.exit_ip || 'Resolved'})` : (preflightResult.error || 'Connection timed out')}</span>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={handlePreflightTest}
                    disabled={isPreflightTesting || !host.trim()}
                    className="px-3.5 py-2 rounded-md bg-secondary hover:bg-secondary/80 border border-border text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw size={12} className={isPreflightTesting ? "animate-spin" : ""} />
                    <span>{isPreflightTesting ? "Testing Ping..." : "Test Connection First"}</span>
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting || !host.trim()}
                    className="px-4 py-2 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                  >
                    <span>Save Proxy</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </motion.form>
            )}
          </AnimatePresence>

          {/* Proxy List Table */}
          {isLoading ? (
            <div className="text-center py-12 text-xs text-muted-foreground animate-pulse">Loading proxy fleet...</div>
          ) : safeProxies.length === 0 ? (
            <div className="text-center py-12 rounded-lg border border-border bg-muted/20 text-xs text-muted-foreground">
              No proxies configured. Outreach will use direct connection.
            </div>
          ) : (
            <div className="space-y-2">
              {safeProxies.map(p => {
                const isTesting = testingId === p.id
                const isHealthy = p.status === 'healthy'
                const isDegraded = p.status === 'degraded'
                const isQuarantined = p.status === 'quarantined'

                return (
                  <div
                    key={p.id}
                    className="p-3.5 rounded-lg bg-card border border-border hover:border-border/80 transition-all flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "w-2.5 h-2.5 rounded-full shrink-0",
                        isHealthy ? "bg-emerald-500 dark:bg-emerald-400 shadow-xs shadow-emerald-500/50" : isDegraded ? "bg-amber-400" : isQuarantined ? "bg-sky-500 shadow-xs shadow-sky-500/50" : "bg-destructive"
                      )} />

                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-foreground font-mono truncate">{p.host}:{p.port}</span>
                          <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded-md bg-muted border border-border text-muted-foreground">
                            {p.protocol}
                          </span>
                          {p.country_code && (
                            <span className="text-[10px] font-bold px-1.5 py-0.2 rounded-md bg-primary/10 border border-primary/20 text-primary">
                              {p.country_code}
                            </span>
                          )}
                          {isQuarantined && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-sky-500/20 border border-sky-500/30 text-sky-600 dark:text-sky-300 flex items-center gap-1">
                              <AlertTriangle size={10} className="text-sky-500 dark:text-sky-400" />
                              Quarantined
                            </span>
                          )}
                          <span className="text-[10px] text-muted-foreground truncate">({p.provider})</span>
                        </div>

                        <div className="flex items-center gap-2 mt-0.5 text-[11px] text-muted-foreground">
                          <span>Exit IP: <strong className="text-foreground font-mono">{p.exit_ip || p.host}</strong></span>
                          <span>·</span>
                          <span>Latency: <strong className={cn(
                            "font-mono font-bold",
                            (p.latency_ms || 999) < 300 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-500 dark:text-amber-400"
                          )}>{p.latency_ms ? `${p.latency_ms}ms` : 'Untested'}</strong></span>
                          {isQuarantined && p.quarantine_reason && (
                            <>
                              <span>·</span>
                              <span className="text-sky-500 dark:text-sky-400/90 italic">Cooldown: {p.quarantine_reason}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleTestProxy(p.id)}
                        disabled={isTesting}
                        className="px-2.5 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 border border-border text-foreground text-[11px] font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                        title="Ping proxy latency and check connection"
                      >
                        <RefreshCw size={11} className={isTesting ? "animate-spin text-primary" : "text-muted-foreground"} />
                        <span>{isTesting ? "Testing..." : "Ping"}</span>
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-border bg-muted/20 flex items-center justify-between text-xs text-muted-foreground shrink-0">
          <span>Enterprise residential IP routing active for all background outreach.</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-md bg-secondary hover:bg-secondary/80 border border-border text-foreground font-semibold transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </motion.div>
    </div>
  )
}
