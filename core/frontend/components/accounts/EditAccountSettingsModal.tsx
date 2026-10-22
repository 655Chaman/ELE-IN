import React, { useState, useMemo } from 'react'
import { motion } from 'motion/react'
import { X, Sliders, Shield, AlertTriangle, RefreshCw, Server, ArrowRight } from 'lucide-react'
import useSWR from 'swr'
import { toast } from 'sonner'
import { fetcher } from '@/lib/apiClient'
import { useHRAccountsStore, type LinkedInAccount } from '@accounts/eiAccountsStore'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePaywall } from '@/contexts/PaywallContext'
import { cn } from '@/lib/utils'

interface EditAccountSettingsModalProps {
  account: LinkedInAccount
  onClose: () => void
  onSuccess?: () => void
}

export function EditAccountSettingsModal({ account, onClose, onSuccess }: EditAccountSettingsModalProps) {
  const { updateAccount } = useHRAccountsStore()
  const { openPaywall } = usePaywall()

  const [name, setName] = useState(account.name || '')
  const [dailyLimit, setDailyLimit] = useState(account.dailyLimit || 20)
  const [messageLimit, setMessageLimit] = useState(account.messageLimit || 40)
  const [proxyId, setProxyId] = useState<string>(account.proxyId || 'none')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch available workspace proxies
  const { data: proxies } = useSWR<any[]>('/api/elein/proxies/health', fetcher)
  const { data: billing } = useSWR<{ tier?: string; tier_limits?: { can_use_custom_proxies?: boolean } }>(
    '/api/elein/workspaces/billing',
    fetcher
  )
  const isProxyLocked = Boolean(billing && !billing.tier_limits?.can_use_custom_proxies)

  // Layer 2 Paranoia: Close on Escape key when not loading
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, loading])

  // Paranoia Layer 2: Detect unsaved changes (dirty checking)
  const isDirty = useMemo(() => {
    const currentProxy = account.proxyId || 'none'
    return (
      name.trim() !== (account.name || '').trim() ||
      Number(dailyLimit) !== (account.dailyLimit || 20) ||
      Number(messageLimit) !== (account.messageLimit || 40) ||
      proxyId !== currentProxy
    )
  }, [name, dailyLimit, messageLimit, proxyId, account])

  const isHighConnectVolume = dailyLimit > 40
  const isHighMessageVolume = messageLimit > 80

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Account name cannot be empty')
      return
    }

    if (dailyLimit < 1 || dailyLimit > 100) {
      setError('Daily connection limit must be between 1 and 100')
      return
    }

    if (messageLimit < 1 || messageLimit > 150) {
      setError('Daily message limit must be between 1 and 150')
      return
    }

    if (!isDirty) {
      onClose()
      return
    }

    setLoading(true)
    setError(null)

    try {
      await updateAccount(account.id, {
        name: name.trim(),
        dailyLimit: Number(dailyLimit),
        messageLimit: Number(messageLimit),
        proxyId: proxyId === 'none' ? 'none' : proxyId,
      })

      toast.success('Account settings updated successfully', {
        description: `Daily limits set to ${dailyLimit} connects / ${messageLimit} messages.`
      })
      onSuccess?.()
      onClose()
    } catch (err: any) {
      setError(err?.message || 'Failed to update account settings')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 font-sans">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className="w-full max-w-lg rounded-2xl bg-card border border-border shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-2rem)]"
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-border/40">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Sliders size={16} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-foreground">Edit Account Settings</h2>
              <p className="text-[11px] text-muted-foreground truncate max-w-[280px]">
                {account.name} {account.profileUrl ? `· ${account.profileUrl}` : ''}
              </p>
            </div>
          </div>
          <button
            type="button"
            disabled={loading}
            onClick={onClose}
            className="w-7 h-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center justify-center cursor-pointer disabled:opacity-50"
          >
            <X size={15} />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSave} className="p-6 space-y-5 overflow-y-auto">
          {error && (
            <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs flex items-center gap-2">
              <AlertTriangle size={14} className="shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Account Display Name */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-foreground flex items-center justify-between">
              <span>Sender Label</span>
              <span className="text-[10px] text-muted-foreground font-normal">Internal friendly name</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Alex Vance (Enterprise Sales)"
              className="w-full h-9 rounded-lg bg-background border border-input px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary transition-all"
              maxLength={255}
            />
          </div>

          {/* Daily Connection Requests Limit */}
          <div className="space-y-2 p-3.5 rounded-xl bg-muted/30 border border-border/40">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-foreground">Daily Connection Limit</span>
                <p className="text-[10px] text-muted-foreground">Safe recommendation: 20-30 invites per day</p>
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={dailyLimit}
                  onChange={(e) => setDailyLimit(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
                  className="w-14 h-8 rounded-lg bg-background border border-input text-center text-xs font-bold text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <span className="text-xs text-muted-foreground">/day</span>
              </div>
            </div>

            <input
              type="range"
              min={1}
              max={100}
              value={dailyLimit}
              onChange={(e) => setDailyLimit(parseInt(e.target.value))}
              className="w-full accent-primary h-1.5 bg-muted rounded-lg cursor-pointer"
            />

            {isHighConnectVolume && (
              <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-[11px] flex items-start gap-2">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                <span>
                  High invite volume: Setting daily invites above 40 increases the risk of temporary LinkedIn restrictions. Safe warmup is recommended.
                </span>
              </div>
            )}
          </div>

          {/* Daily Direct Message Limit */}
          <div className="space-y-2 p-3.5 rounded-xl bg-muted/30 border border-border/40">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-foreground">Daily Message Limit</span>
                <p className="text-[10px] text-muted-foreground">Safe recommendation: 30-50 messages per day</p>
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={1}
                  max={150}
                  value={messageLimit}
                  onChange={(e) => setMessageLimit(Math.max(1, Math.min(150, parseInt(e.target.value) || 1)))}
                  className="w-14 h-8 rounded-lg bg-background border border-input text-center text-xs font-bold text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <span className="text-xs text-muted-foreground">/day</span>
              </div>
            </div>

            <input
              type="range"
              min={1}
              max={150}
              value={messageLimit}
              onChange={(e) => setMessageLimit(parseInt(e.target.value))}
              className="w-full accent-primary h-1.5 bg-muted rounded-lg cursor-pointer"
            />

            {isHighMessageVolume && (
              <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-[11px] flex items-start gap-2">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                <span>
                  High message volume: Sending over 80 messages per day may trigger LinkedIn automated rate limiting.
                </span>
              </div>
            )}
          </div>

          {/* Proxy Assignment */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Server size={13} className="text-primary" />
                <span>Assigned Dedicated Proxy</span>
              </label>
              {isProxyLocked && (
                <button
                  type="button"
                  onClick={() => openPaywall({ featureName: "Dedicated Proxy Pool Routing" })}
                  className="text-[10px] font-bold text-amber-600 dark:text-amber-400 hover:underline cursor-pointer"
                >
                  Pro Feature
                </button>
              )}
            </div>

            <Select
              value={proxyId}
              onValueChange={(val) => {
                if (isProxyLocked && val !== 'none') {
                  openPaywall({ featureName: "Dedicated Proxy Pool Routing" })
                  return
                }
                setProxyId(val)
              }}
            >
              <SelectTrigger className="w-full bg-background border-input px-3 py-2 text-xs text-foreground h-9">
                <SelectValue placeholder="Select Proxy" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Proxy (Direct Workspace Connection)</SelectItem>
                {proxies?.map((p: any) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.provider || "Residential"} - {p.country_code || "US"} ({p.host})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[10px] text-muted-foreground">
              Route this sender's browser session through a dedicated residential or static proxy to avoid IP rotation flags.
            </p>
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-border/40">
            <button
              type="button"
              disabled={loading}
              onClick={onClose}
              className="px-3.5 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !isDirty || !name.trim()}
              className={cn(
                "px-4 py-1.5 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 cursor-pointer shadow-xs",
                isDirty && name.trim() && !loading
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "bg-muted text-muted-foreground cursor-not-allowed opacity-60"
              )}
            >
              {loading ? (
                <>
                  <RefreshCw size={13} className="animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <>
                  <span>Save Changes</span>
                  <ArrowRight size={13} />
                </>
              )}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}
