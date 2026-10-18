import { useState, useMemo, useEffect } from 'react'
import useSWR from 'swr'
import { fetcher, fetchWithAuth } from '@/lib/apiClient'
import { 
  CheckCircle, CheckCircle2, XCircle, Loader2, Inbox, ChevronRight, Flame,
  RefreshCw, Sparkles, HelpCircle, ShieldAlert, CalendarCheck, RotateCcw, 
  Zap, ArrowRight, Search, CheckSquare, Square, X, AlertTriangle,
  ShieldCheck, Clock, MessageSquare
} from 'lucide-react'
import { toast } from 'sonner'
import { formatDistanceToNow } from 'date-fns'
import { ElesiumLogo } from './components/ElesiumLogo'

interface ApprovalItem {
  id: string
  account_id: string
  sender_name: string
  intent: string
  heat_score: number
  ai_draft: string | null
  status: 'pending' | 'approved' | 'skipped'
  created_at: string
  thread_messages_json?: any[]
}

interface ApprovalListResponse {
  data: ApprovalItem[]
  count: number
}

interface EleInApprovalsProps {
  onGoToConversations?: () => void
}

function HeatBadge({ score }: { score: number }) {
  const isHot = score >= 75
  const isWarm = score >= 40

  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-border bg-muted/60 text-foreground text-xs font-semibold">
      <Flame size={11} className={isHot ? 'text-primary' : isWarm ? 'text-muted-foreground' : 'text-muted-foreground/60'} />
      <span>{Math.round(score)}% Heat</span>
    </span>
  )
}

function IntentBadge({ intent }: { intent: string }) {
  const map: Record<string, { label: string; icon: any }> = {
    interested: { label: 'High Intent', icon: Sparkles },
    objection: { label: 'Objection Raised', icon: ShieldAlert },
    question: { label: 'Inquiry', icon: HelpCircle },
    meeting_request: { label: 'Meeting Request', icon: CalendarCheck },
    unknown: { label: intent || 'Pending Review', icon: Sparkles },
  }
  const cfg = map[intent] ?? map.unknown
  const Icon = cfg.icon
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-border bg-muted text-foreground text-xs font-medium tracking-wide">
      <Icon size={10} className="text-primary" />
      {cfg.label}
    </span>
  )
}

export function EleInApprovals({ onGoToConversations }: EleInApprovalsProps = {}) {
  const { data, error, isLoading, mutate } = useSWR<ApprovalListResponse>(
    '/api/approvals?status=pending&limit=100',
    fetcher,
    { refreshInterval: 30_000 }
  )

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draftText, setDraftText] = useState<string>('')
  const [isActing, setIsActing] = useState(false)
  const [showOriginalComparison, setShowOriginalComparison] = useState(false)

  // ── Layer 0 & 2: Filters, Search & Multi-Select ──
  const [searchQuery, setSearchQuery] = useState('')
  const [intentFilter, setIntentFilter] = useState<string>('ALL')
  const [heatFilter, setHeatFilter] = useState<'ALL' | 'HOT' | 'WARM'>('ALL')
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set())
  const [isBatchActing, setIsBatchActing] = useState(false)
  const [isAutoApproving, setIsAutoApproving] = useState(false)

  // Fetch full details (including thread) for the selected item
  const { data: detailData } = useSWR<ApprovalItem>(
    selectedId ? `/api/approvals/${selectedId}` : null,
    fetcher
  )

  const items = data?.data ?? []

  // Filtered Items Memo (Layer 0 Foundational)
  const filteredItems = useMemo(() => {
    return items.filter(item => {
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchesName = item.sender_name.toLowerCase().includes(q)
        const matchesDraft = (item.ai_draft || '').toLowerCase().includes(q)
        if (!matchesName && !matchesDraft) return false
      }

      // Intent filter
      if (intentFilter !== 'ALL' && item.intent !== intentFilter) {
        return false
      }

      // Heat filter
      if (heatFilter === 'HOT' && item.heat_score < 75) return false
      if (heatFilter === 'WARM' && (item.heat_score < 40 || item.heat_score >= 75)) return false

      return true
    })
  }, [items, searchQuery, intentFilter, heatFilter])

  // Prefer the detailed data if we have it, otherwise fallback to list data
  const selected = (detailData?.id === selectedId ? detailData : items.find(i => i.id === selectedId)) ?? null

  const handleSelect = (item: ApprovalItem) => {
    setSelectedId(item.id)
    setDraftText(item.ai_draft ?? '')
    setShowOriginalComparison(false)
  }

  // Auto-select first item on load if none selected
  useEffect(() => {
    if (!selectedId && filteredItems.length > 0) {
      handleSelect(filteredItems[0])
    }
  }, [filteredItems, selectedId])

  // ── Multi-Select Handlers (Layer 0 & 2) ──
  const handleToggleSelectId = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelectedItemIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleSelectAllFiltered = () => {
    if (selectedItemIds.size === filteredItems.length) {
      setSelectedItemIds(new Set())
    } else {
      setSelectedItemIds(new Set(filteredItems.map(i => i.id)))
    }
  }

  const handleSelectHotItems = () => {
    const hotIds = filteredItems.filter(i => i.heat_score >= 75).map(i => i.id)
    setSelectedItemIds(new Set(hotIds))
    toast.info(`Selected ${hotIds.length} high-heat items (≥75%)`)
  }

  // ── Quick Tune Rewrite Presets ──
  const applyRewritePreset = (type: 'concise' | 'calendar' | 'soft' | 'reset') => {
    if (!selected) return
    if (type === 'reset') {
      setDraftText(selected.ai_draft ?? '')
      toast.info('Reset to original AI draft')
      return
    }

    if (type === 'concise') {
      const sentences = draftText.split(/(?<=[.?!])\s+/).filter(Boolean)
      if (sentences.length > 2) {
        setDraftText(sentences.slice(0, 2).join(' '))
        toast.success('Trimmed to punchy 2-sentence draft')
      } else {
        toast.info('Draft is already concise')
      }
    } else if (type === 'calendar') {
      const callCTA = "\n\nWould you be open to a quick 15-min chat next Tuesday or Thursday? Feel free to grab a time here if easier: [Your Booking Link]"
      if (!draftText.includes("15-min") && !draftText.includes("Booking Link")) {
        setDraftText(draftText.trim() + callCTA)
        toast.success('Appended calendar scheduling invitation')
      }
    } else if (type === 'soft') {
      let updated = draftText
      if (!updated.toLowerCase().includes("no worries")) {
        updated = updated.trim() + " Completely understand if your plate is full right now - happy to circle back down the line."
        setDraftText(updated)
        toast.success('Softened tone with consultative closing')
      }
    }
  }

  // ── Autonomous Auto-Approval for High-Heat Responses ──
  const handleAutoApproveHighHeat = async () => {
    if (isAutoApproving) return
    setIsAutoApproving(true)
    try {
      const res = await fetchWithAuth('/api/approvals/auto-approve-high-heat', {
        method: 'POST',
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Auto-approval encountered an issue')
      }
      const result = await res.json()
      toast.success(`Autonomous AI dispatched ${result.approved_count} high-heat replies!`)
      mutate()
    } catch (err: any) {
      toast.error(err.message || 'Failed to run high-heat auto-approval')
    } finally {
      setIsAutoApproving(false)
    }
  }

  // ── Single Item Actions ──
  const handleApprove = async () => {
    if (!selected || isActing) return
    setIsActing(true)
    const currentId = selected.id
    try {
      const res = await fetchWithAuth(`/api/approvals/${currentId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edited_message: draftText || null }),
      })
      if (res.ok) {
        toast.success('Reply approved. Queued for delivery on LinkedIn')
        // Advance to next pending item for continuous operator momentum
        const remaining = filteredItems.filter(i => i.id !== currentId)
        if (remaining.length > 0) {
          const next = remaining[0]
          setSelectedId(next.id)
          setDraftText(next.ai_draft ?? '')
        } else {
          setSelectedId(null)
          setDraftText('')
        }
        mutate()
      } else {
        const err = await res.json().catch(() => ({}))
        toast.error(err?.detail ?? 'Failed to approve reply')
      }
    } catch {
      toast.error('Network error. Please try again')
    } finally {
      setIsActing(false)
    }
  }

  const handleReject = async () => {
    if (!selected || isActing) return
    setIsActing(true)
    const currentId = selected.id
    try {
      const res = await fetchWithAuth(`/api/approvals/${currentId}/reject`, { method: 'POST' })
      if (res.ok) {
        toast.info('Reply rejected and skipped')
        const remaining = filteredItems.filter(i => i.id !== currentId)
        if (remaining.length > 0) {
          const next = remaining[0]
          setSelectedId(next.id)
          setDraftText(next.ai_draft ?? '')
        } else {
          setSelectedId(null)
          setDraftText('')
        }
        mutate()
      } else {
        toast.error('Failed to reject reply')
      }
    } catch {
      toast.error('Network error. Please try again')
    } finally {
      setIsActing(false)
    }
  }

  // ── Batch Actions (Layer 1 Paranoia: Atomic Server-Side Execution with Error Resilience) ──
  const handleBatchApprove = async () => {
    if (selectedItemIds.size === 0 || isBatchActing) return
    setIsBatchActing(true)
    const idsToApprove = Array.from(selectedItemIds)

    try {
      const res = await fetchWithAuth('/api/approvals/batch-action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'approve', approval_ids: idsToApprove })
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Failed to batch approve replies')
      }
      const result = await res.json()
      toast.success(`Batch approved ${result.processed_count} replies! Dispatched to LinkedIn queue.`)
      setSelectedItemIds(new Set())
      mutate()
    } catch (err: any) {
      toast.error(err.message || 'Failed to batch approve replies')
    } finally {
      setIsBatchActing(false)
    }
  }

  const handleBatchReject = async () => {
    if (selectedItemIds.size === 0 || isBatchActing) return
    setIsBatchActing(true)
    const idsToReject = Array.from(selectedItemIds)

    try {
      const res = await fetchWithAuth('/api/approvals/batch-action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reject', approval_ids: idsToReject })
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Failed to batch reject replies')
      }
      const result = await res.json()
      toast.info(`Rejected and skipped ${result.processed_count} replies.`)
      setSelectedItemIds(new Set())
      mutate()
    } catch (err: any) {
      toast.error(err.message || 'Failed to batch reject replies')
    } finally {
      setIsBatchActing(false)
    }
  }

  // ── Keyboard Shortcuts (Layer 0 Operator Flow) ──
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // If typing inside an input/textarea and presses Cmd+Enter / Ctrl+Enter: Approve
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        handleApprove()
        return
      }

      // If active inside textarea, don't hijack simple letters or arrow keys
      const activeTag = document.activeElement?.tagName?.toLowerCase()
      if (activeTag === 'textarea' || activeTag === 'input') return

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        const currentIdx = filteredItems.findIndex(i => i.id === selectedId)
        if (currentIdx < filteredItems.length - 1) {
          handleSelect(filteredItems[currentIdx + 1])
        }
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        const currentIdx = filteredItems.findIndex(i => i.id === selectedId)
        if (currentIdx > 0) {
          handleSelect(filteredItems[currentIdx - 1])
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [filteredItems, selectedId, handleApprove])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        <Loader2 className="animate-spin mr-2" size={18} /> Loading approvals…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-destructive text-sm gap-2">
        <AlertTriangle size={16} />
        <span>Failed to load approvals. Please verify connection and retry.</span>
      </div>
    )
  }

  const isDraftEdited = selected && draftText !== (selected.ai_draft ?? '')
  const charDelta = selected?.ai_draft ? draftText.length - selected.ai_draft.length : 0

  return (
    <div className="flex h-full min-h-[540px] /* ds-allow-hardcode */ border border-border rounded-xl overflow-hidden bg-card shadow-sm">
      {/* ── LEFT: Pending list & Filters ─────────────────────────────────────── */}
      <div className="w-[340px] /* ds-allow-hardcode */ shrink-0 border-r border-border bg-card flex flex-col">
        {/* Header & Refresh */}
        <div className="p-3.5 border-b border-border bg-card flex flex-col gap-2.5">
          <div className="flex items-center justify-between gap-1.5">
            <div className="flex items-center gap-1.5 min-w-0">
              <ElesiumLogo size={16} className="shrink-0" />
              <span className="text-sm font-semibold text-foreground whitespace-nowrap">AI Approvals</span>
              <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground border border-border shrink-0">
                {items.length}
              </span>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={handleAutoApproveHighHeat}
                disabled={isAutoApproving}
                className="px-2 py-1 text-xs font-medium rounded-md bg-muted hover:bg-muted/80 text-foreground border border-border transition-all flex items-center gap-1 cursor-pointer shadow-2xs whitespace-nowrap"
                title="1-click dispatch for high-heat replies (≥75%)"
              >
                {isAutoApproving ? <Loader2 size={11} className="animate-spin text-primary" /> : <Flame size={11} className="text-primary" />}
                <span>Auto-Dispatch</span>
              </button>
              <button 
                onClick={() => mutate()} 
                className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted border border-border cursor-pointer shrink-0"
                title="Refresh queue"
                aria-label="Refresh queue"
              >
                <RefreshCw size={13} />
              </button>
            </div>
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Filter by prospect name..."
              className="w-full bg-background border border-border rounded-md pl-8 pr-7 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/50 transition-colors"
            />
            {searchQuery && (
              <button 
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <X size={12} />
              </button>
            )}
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none text-xs">
            <button
              onClick={() => setIntentFilter('ALL')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 cursor-pointer ${
                intentFilter === 'ALL' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'bg-muted/60 text-muted-foreground hover:text-foreground border border-border'
              }`}
            >
              All Intents
            </button>
            <button
              onClick={() => setIntentFilter('interested')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 cursor-pointer ${
                intentFilter === 'interested' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'bg-muted/60 text-muted-foreground hover:text-foreground border border-border'
              }`}
            >
              High Intent
            </button>
            <button
              onClick={() => setIntentFilter('objection')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 cursor-pointer ${
                intentFilter === 'objection' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'bg-muted/60 text-muted-foreground hover:text-foreground border border-border'
              }`}
            >
              Objection
            </button>
            <button
              onClick={() => setHeatFilter(heatFilter === 'HOT' ? 'ALL' : 'HOT')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 cursor-pointer flex items-center gap-1 ${
                heatFilter === 'HOT' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'bg-muted/60 text-muted-foreground hover:text-foreground border border-border'
              }`}
            >
              <Flame size={12} className={heatFilter === 'HOT' ? 'text-primary-foreground' : 'text-primary'} />
              <span>Hot Only</span>
            </button>
          </div>

          {/* Multi-Select Toolbar (Layer 0 & 2) */}
          {filteredItems.length > 0 && (
            <div className="pt-2 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
              <button
                type="button"
                onClick={handleSelectAllFiltered}
                className="flex items-center gap-1 hover:text-foreground cursor-pointer font-medium"
              >
                {selectedItemIds.size === filteredItems.length && filteredItems.length > 0 ? (
                  <CheckSquare size={13} className="text-primary" />
                ) : (
                  <Square size={13} />
                )}
                <span>Select All ({filteredItems.length})</span>
              </button>

              <button
                type="button"
                onClick={handleSelectHotItems}
                className="text-primary hover:underline font-semibold cursor-pointer flex items-center gap-1"
              >
                <span>Select Hot (≥75%)</span>
              </button>
            </div>
          )}
        </div>

        {/* Pending List Items */}
        {filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 gap-2.5 text-muted-foreground px-5 text-center p-6">
            <div className="w-10 h-10 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <CheckCircle2 size={20} />
            </div>
            <p className="text-sm font-semibold text-foreground">Queue is Clear</p>
            <p className="text-xs text-muted-foreground max-w-56 leading-relaxed">
              No pending AI replies waiting for review. Incoming replies from active campaigns will stage here automatically.
            </p>
          </div>
        ) : (
          <ul className="flex-1 overflow-y-auto divide-y divide-border/60">
            {filteredItems.map(item => {
              const isChecked = selectedItemIds.has(item.id)
              const isCurrent = selectedId === item.id

              return (
                <li
                  key={item.id}
                  onClick={() => handleSelect(item)}
                  className={`p-3.5 cursor-pointer hover:bg-accent/40 transition-all flex items-start gap-2.5 ${
                    isCurrent ? 'bg-primary/10 border-l-2 border-l-primary' : 'border-l-2 border-l-transparent'
                  }`}
                >
                  {/* Select Checkbox */}
                  <div
                    onClick={(e) => handleToggleSelectId(item.id, e)}
                    className="pt-0.5 cursor-pointer text-muted-foreground hover:text-foreground shrink-0"
                  >
                    {isChecked ? (
                      <CheckSquare size={14} className="text-primary" />
                    ) : (
                      <Square size={14} />
                    )}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <p className="text-xs font-bold text-foreground truncate">{item.sender_name}</p>
                      <span className="text-xs text-muted-foreground font-mono shrink-0">
                        {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
                      <IntentBadge intent={item.intent} />
                      <HeatBadge score={item.heat_score} />
                    </div>

                    <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                      {item.ai_draft || 'No draft text'}
                    </p>
                  </div>

                  <ChevronRight size={14} className="text-muted-foreground shrink-0 mt-1 opacity-60" />
                </li>
              )
            })}
          </ul>
        )}

        {/* ── Sticky Batch Action Dock (Layer 0 & 2) ── */}
        {selectedItemIds.size > 0 && (
          <div className="p-3 border-t border-border bg-background/95 backdrop-blur-md flex items-center justify-between gap-2 shrink-0 animate-in fade-in duration-200">
            <span className="text-xs font-bold text-foreground">
              {selectedItemIds.size} selected
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleBatchReject}
                disabled={isBatchActing}
                className="px-2.5 py-1 text-xs font-semibold rounded-md border border-border text-muted-foreground hover:text-destructive hover:border-destructive transition-colors disabled:opacity-50 cursor-pointer flex items-center gap-1"
              >
                <span>Reject ({selectedItemIds.size})</span>
              </button>
              <button
                type="button"
                onClick={handleBatchApprove}
                disabled={isBatchActing}
                className="px-3 py-1 text-xs font-bold rounded-md bg-primary hover:bg-primary/90 text-primary-foreground shadow-xs transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
              >
                {isBatchActing ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Zap size={12} />
                )}
                <span>Approve ({selectedItemIds.size})</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── RIGHT: Review pane ─────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-card">
        {selected ? (
          <>
            {/* Header */}
            <div className="px-6 py-4 border-b border-border bg-card flex items-center justify-between shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-base text-foreground">{selected.sender_name}</h3>
                  <IntentBadge intent={selected.intent} />
                  <HeatBadge score={selected.heat_score} />
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                  <span>Queued {formatDistanceToNow(new Date(selected.created_at), { addSuffix: true })}</span>
                  {selected.account_id && (
                    <>
                      <span>•</span>
                      <span className="font-mono text-xs">Account: {selected.account_id.slice(0, 8)}</span>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleReject}
                  disabled={isActing}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-semibold text-muted-foreground hover:text-destructive hover:border-destructive transition-colors disabled:opacity-50 cursor-pointer"
                  title="Reject and skip (Cmd+Backspace)"
                >
                  <XCircle size={13} />
                  <span>Reject</span>
                </button>
                <button
                  onClick={handleApprove}
                  disabled={isActing || !draftText.trim()}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all disabled:opacity-50 shadow-xs cursor-pointer"
                  title="Approve & Send (Cmd+Enter)"
                >
                  {isActing ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
                  <span>Approve &amp; Next</span>
                  <ArrowRight size={12} className="ml-0.5 opacity-80" />
                </button>
              </div>
            </div>

            {/* Conversation Thread */}
            {selected.thread_messages_json && selected.thread_messages_json.length > 0 && (
              <div className="px-6 py-3.5 border-b border-border bg-muted/20 overflow-y-auto max-h-52 shrink-0">
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">
                  Full Conversation Thread
                </p>
                <div className="space-y-2">
                  {selected.thread_messages_json.map((msg: any, i: number) => (
                    <div
                      key={i}
                      className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[75%] px-3.5 py-2.5 rounded-xl text-xs leading-relaxed ${
                          msg.direction === 'outbound'
                            ? 'bg-primary text-primary-foreground border border-primary/20'
                            : 'bg-muted text-foreground border border-border'
                        }`}
                      >
                        {msg.message_text ?? msg.text ?? JSON.stringify(msg)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* AI Draft editor with 1-Click Fine-Tune Presets */}
            <div className="flex-1 flex flex-col px-6 py-4 overflow-hidden bg-background">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <ElesiumLogo size={14} />
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    AI Suggested Draft
                  </p>
                  {isDraftEdited && (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-primary/10 text-primary border border-primary/20">
                      Modified ({charDelta > 0 ? `+${charDelta}` : charDelta} chars)
                    </span>
                  )}
                </div>

                {/* Quick Tune Presets */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground uppercase font-semibold mr-1">Tune:</span>
                  <button
                    type="button"
                    onClick={() => applyRewritePreset('concise')}
                    className="px-2 py-0.5 rounded-md border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-all flex items-center gap-1 cursor-pointer"
                    title="Trim down to 2 punchy sentences"
                  >
                    <Zap size={10} className="text-primary" />
                    <span>Concise</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => applyRewritePreset('calendar')}
                    className="px-2 py-0.5 rounded-md border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-all flex items-center gap-1 cursor-pointer"
                    title="Append calendar meeting invite"
                  >
                    <CalendarCheck size={10} className="text-primary" />
                    <span>Propose Call</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => applyRewritePreset('soft')}
                    className="px-2 py-0.5 rounded-md border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-all flex items-center gap-1 cursor-pointer"
                    title="Soften tone into friendly consultative closing"
                  >
                    <Sparkles size={10} className="text-primary" />
                    <span>Soften</span>
                  </button>
                  {isDraftEdited && (
                    <button
                      type="button"
                      onClick={() => applyRewritePreset('reset')}
                      className="px-2 py-0.5 rounded-md text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1 cursor-pointer ml-1"
                      title="Reset back to original AI draft"
                    >
                      <RotateCcw size={10} /> Reset
                    </button>
                  )}
                </div>
              </div>

              {/* Textarea Editor */}
              <textarea
                className="flex-1 w-full resize-none rounded-xl border border-border bg-background p-3.5 text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all font-normal leading-relaxed text-foreground"
                value={draftText}
                onChange={e => setDraftText(e.target.value)}
                placeholder="AI draft will appear here…"
                spellCheck
              />

              {/* Original Draft Comparison Inspector */}
              {showOriginalComparison && selected.ai_draft && (
                <div className="mt-2 p-3 bg-muted/40 rounded-xl border border-border text-xs text-muted-foreground">
                  <span className="font-bold text-foreground text-xs uppercase flex items-center gap-1.5 mb-1">
                    <ElesiumLogo size={12} />
                    Original Unedited AI Draft:
                  </span>
                  <p className="italic leading-relaxed">{selected.ai_draft}</p>
                </div>
              )}

              {/* Review Pane Footer & Keyboard Helpers */}
              <div className="flex items-center justify-between mt-2.5 text-xs text-muted-foreground pt-1">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-primary" />
                    <span>Dispatches directly to LinkedIn inbox</span>
                  </div>
                  {isDraftEdited && (
                    <button
                      type="button"
                      onClick={() => setShowOriginalComparison(!showOriginalComparison)}
                      className="text-primary hover:underline font-medium cursor-pointer"
                    >
                      {showOriginalComparison ? 'Hide original' : 'Compare original'}
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-3">
                  <span className="font-mono">{draftText.length} / 3,000 chars</span>
                  <span className="hidden sm:inline bg-muted px-2 py-0.5 rounded-md border border-border font-mono text-xs">
                    ⌘↵ to Approve
                  </span>
                </div>
              </div>
            </div>
          </>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 p-8 text-center max-w-lg mx-auto">
            <div className="w-14 h-14 rounded-xl bg-muted border border-border flex items-center justify-center text-muted-foreground mb-4 shadow-2xs">
              <ElesiumLogo size={28} />
            </div>
            <h3 className="text-base font-bold text-foreground mb-1.5 flex items-center justify-center gap-2">
              AI Reply Approval Desk
            </h3>
            <p className="text-xs text-muted-foreground mb-6 max-w-md leading-relaxed">
              This desk gives you human-in-the-loop oversight. When prospects reply to your outreach campaigns, the AI pre-drafts replies so you can review, tune, and approve them in seconds before sending.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full text-left mb-6">
              <div className="p-3 rounded-lg bg-muted/40 border border-border">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <ShieldCheck size={13} className="text-primary shrink-0" />
                  <span>Zero Risk</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  No automated replies send without your verification.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-muted/40 border border-border">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Zap size={13} className="text-primary shrink-0" />
                  <span>1-Click Tune</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Instantly trim length, soften tone, or insert calendar links.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-muted/40 border border-border">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Clock size={13} className="text-primary shrink-0" />
                  <span>Rapid Flow</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Clear 20 replies in 60 seconds with hotkeys (J, K, ⌘↵).
                </p>
              </div>
            </div>

            {onGoToConversations && (
              <button
                type="button"
                onClick={onGoToConversations}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all shadow-xs cursor-pointer"
              >
                <MessageSquare size={13} />
                <span>Return to Conversations</span>
              </button>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center flex-1 gap-2 text-muted-foreground p-8 text-center">
            <Inbox size={40} strokeWidth={1.5} className="opacity-30" />
            <h4 className="text-sm font-semibold text-foreground">Select a Pending Reply</h4>
            <p className="text-xs text-muted-foreground max-w-xs leading-relaxed">
              Choose an AI drafted reply from the left column or use batch actions to approve high-confidence responses.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
