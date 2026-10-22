import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import useSWR, { mutate } from 'swr';
import {
  MessageSquare, RefreshCw
} from 'lucide-react';
import { toast } from 'sonner';
import { fetcher, fetchWithAuth } from '@/lib/apiClient';
import { ElesiumLogo } from './components/ElesiumLogo';
import { usePaywall } from '@/contexts/PaywallContext';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import { EleInApprovals } from './EleInApprovals';
import {
  DEAL_STAGES, OUTCOMES, type DealStage, type Message, type ObjectionData,
  type OutcomeType, type ThreadSummary
} from './types';
import { ThreadListPane } from './components/ThreadListPane';
import { ConversationCanvas } from './components/ConversationCanvas';
import { ComposerStation } from './components/ComposerStation';
import { IntelligenceInspector } from './components/IntelligenceInspector';
import { InboxCommandPalette } from './components/InboxCommandPalette';
import { VariableFillModal } from './components/VariableFillModal';
import { TimezoneSlotPickerModal } from './components/TimezoneSlotPickerModal';
import { useInboxKeyboardShortcuts } from './hooks/useInboxKeyboardShortcuts';
import { useUndoSend } from './hooks/useUndoSend';

export function EleInInbox() {
  const navigate = useNavigate();
  const { openTopUp, openPaywall, openMilestoneModal } = usePaywall();
  const { activeWorkspaceId } = useWorkspace();
  const { queueSend } = useUndoSend();

  // Paranoia Layer 0, 1 & 2: Invalidate global credit balance keys when AI or reply activity occurs
  const invalidateCreditBalances = useCallback(() => {
    try {
      mutate('/api/elein/billing/credits/balance');
      mutate('/api/elein/workspaces/billing');
      mutate(
        (key: any) =>
          typeof key === 'string' &&
          (key.startsWith('/api/elein/billing/credits/balance') ||
            key.startsWith('/api/elein/billing') ||
            key.startsWith('/api/elein/workspaces/billing')),
        undefined,
        { revalidate: true }
      );
    } catch {
      // SWR cache invalidation safety
    }
  }, []);

  // ── SWR Data Queries ──
  const { data: threads, mutate: mutateThreads } = useSWR<ThreadSummary[]>(
    '/api/elein/inbox/threads',
    fetcher
  );
  const { data: billingData } = useSWR<{ tier?: string }>(
    '/api/elein/workspaces/billing',
    fetcher
  );
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  const [selectedThreadKey, setSelectedThreadKey] = useState<string | null>(null);
  const [selectedSender, setSelectedSender] = useState<string | null>(null);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'messages' | 'approvals'>('messages');

  const { data: messages, mutate: mutateMessages } = useSWR<Message[]>(
    selectedSender
      ? `/api/elein/inbox/threads/${encodeURIComponent(selectedSender)}?lead_id=${encodeURIComponent(
          selectedLeadId || 'unknown'
        )}`
      : null,
    fetcher
  );

  const { data: approvalCount } = useSWR<{ count: number }>(
    '/api/approvals?status=pending&limit=1',
    fetcher,
    { refreshInterval: 30_000 }
  );

  const { data: accountsData } = useSWR<any[]>('/api/elein/accounts', fetcher);
  const accounts = Array.isArray(accountsData) ? accountsData : [];
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const activeAccountId = selectedAccountId || (accounts.length > 0 ? accounts[0].id : '');

  // ── Layout State (Clean 2-Column Default; Inspector Opens on Demand) ──
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isVariableModalOpen, setIsVariableModalOpen] = useState(false);
  const [isSlotPickerOpen, setIsSlotPickerOpen] = useState(false);
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  // ── Multi-Stage Playwright Sync State ──
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStage, setSyncStage] = useState<1 | 2 | 3>(1);
  const [syncElapsed, setSyncElapsed] = useState(0);
  const syncTimerRef = useRef<NodeJS.Timeout | null>(null);
  const syncAbortControllerRef = useRef<AbortController | null>(null);
  const isSyncingRef = useRef(false);

  // ── Search & Filter State ──
  const [searchQuery, setSearchQuery] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState<'ALL' | 'INBOUND' | OutcomeType>('ALL');
  const [dealStageFilter, setDealStageFilter] = useState<'ALL' | DealStage>('ALL');

  // Pipeline outcomes cached by workspace
  const activeWorkspace = activeWorkspaceId || 'default';
  const outcomesStorageKey = `elein_inbox_outcomes_${activeWorkspace}`;

  const [threadOutcomes, setThreadOutcomes] = useState<Record<string, OutcomeType>>(() => {
    if (typeof window === 'undefined') return {};
    try {
      const saved = localStorage.getItem(`elein_inbox_outcomes_${activeWorkspaceId || 'default'}`);
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const handleSetOutcome = (threadKey: string, outcome: OutcomeType | null) => {
    setThreadOutcomes((prev) => {
      const next = { ...prev };
      if (!outcome) {
        delete next[threadKey];
      } else {
        next[threadKey] = outcome;
      }
      try {
        localStorage.setItem(outcomesStorageKey, JSON.stringify(next));
      } catch (e) {
        console.error('Failed to persist outcome', e);
      }
      return next;
    });

    if (outcome) {
      toast.success(`Marked as ${OUTCOMES[outcome].label}`);
    } else {
      toast.info('Outcome tag cleared');
    }
  };

  // ── Production Inbox: Live Threads Only ──
  const safeThreads = Array.isArray(threads) ? threads : [];

  // ── Resizable Thread List Width ──
  const [threadListWidth, setThreadListWidth] = useState<number>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('elein_inbox_thread_list_width');
      if (saved) {
        const parsed = parseInt(saved, 10);
        if (!isNaN(parsed) && parsed >= 260 && parsed <= 500) return parsed;
      }
    }
    return 320;
  });
  const isDraggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(320);

  const handleMouseDownResize = (e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = threadListWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const delta = moveEvent.clientX - startXRef.current;
      const nextWidth = Math.min(500, Math.max(260, startWidthRef.current + delta));
      setThreadListWidth(nextWidth);
    };

    const handleMouseUp = () => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      setThreadListWidth((curr) => {
        try {
          localStorage.setItem('elein_inbox_thread_list_width', String(curr));
        } catch {
          // ignore storage error
        }
        return curr;
      });
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  useEffect(() => {
    return () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, []);

  // ── Composer & Memory State ──
  const [replyText, setReplyText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isDraftingAI, setIsDraftingAI] = useState(false);
  const [activeAIIntent, setActiveAIIntent] = useState<string | null>(null);
  const [savedDraftBeforeAI, setSavedDraftBeforeAI] = useState<string | null>(null);
  const [sendOnEnter, setSendOnEnter] = useState(true);

  // ── Deal Pipeline Stages & AI Battlecard State ──
  const [dealStagesByLead, setDealStagesByLead] = useState<Record<string, DealStage>>({});
  const [isGeneratingBattlecard, setIsGeneratingBattlecard] = useState(false);
  const [activeBattlecardTone, setActiveBattlecardTone] = useState<
    'challenger' | 'consultative' | 'casual' | null
  >(null);
  const [isInsertingSlots, _setIsInsertingSlots] = useState(false);

  // Thread drafts store in session
  const draftsByThreadRef = useRef<Record<string, string>>({});
  const isSendingRef = useRef(false);
  const isDraftingRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const previousDraftRef = useRef<string>('');

  // Paranoia Layer 1 & 2: Flush selected thread, cached drafts, and reload outcomes on workspace transition
  const prevWorkspaceRef = useRef<string | null>(activeWorkspaceId);
  useEffect(() => {
    if (prevWorkspaceRef.current !== activeWorkspaceId) {
      prevWorkspaceRef.current = activeWorkspaceId;
      setSelectedThreadKey(null);
      setSelectedSender(null);
      setSelectedLeadId(null);
      setReplyText('');
      setSavedDraftBeforeAI(null);
      previousDraftRef.current = '';
      draftsByThreadRef.current = {};
      setSearchQuery('');
      setOutcomeFilter('ALL');
      setDealStageFilter('ALL');

      const newKey = `elein_inbox_outcomes_${activeWorkspaceId || 'default'}`;
      try {
        const saved = localStorage.getItem(newKey);
        setThreadOutcomes(saved ? JSON.parse(saved) : {});
      } catch {
        setThreadOutcomes({});
      }

      mutateThreads();
    }
  }, [activeWorkspaceId, mutateThreads]);

  // Milestone detection
  useEffect(() => {
    if (isPro || !threads || threads.length === 0) return;
    const workspaceId =
      typeof window !== 'undefined'
        ? localStorage.getItem('elein_active_workspace') || 'default'
        : 'default';
    const dismissedKey = `elein_milestone_dismissed_${workspaceId}`;
    const claimedKey = `elein_milestone_claimed_${workspaceId}`;

    if (localStorage.getItem(dismissedKey) || localStorage.getItem(claimedKey)) {
      return;
    }

    const firstInboundThread = threads.find((t) => t.direction === 'inbound');
    if (firstInboundThread) {
      const timer = setTimeout(() => {
        openMilestoneModal({
          milestoneType: 'first_reply',
          prospectName: firstInboundThread.sender_name || 'Your prospect',
          campaignName: 'Outreach Campaign',
        });
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [threads, isPro, openMilestoneModal]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (syncTimerRef.current) clearInterval(syncTimerRef.current);
      if (syncAbortControllerRef.current) syncAbortControllerRef.current.abort();
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  // ── Playwright Multi-Stage Sync ──
  const handleCancelSync = () => {
    if (syncAbortControllerRef.current) {
      syncAbortControllerRef.current.abort();
      syncAbortControllerRef.current = null;
    }
    if (syncTimerRef.current) {
      clearInterval(syncTimerRef.current);
      syncTimerRef.current = null;
    }
    isSyncingRef.current = false;
    setIsSyncing(false);
    toast.info('Inbox sync cancelled.');
  };

  const handleSync = async () => {
    if (!activeAccountId) {
      toast.error('Please connect an active LinkedIn account first.');
      navigate('/elein/accounts');
      return;
    }
    if (isSyncingRef.current) return;

    isSyncingRef.current = true;
    setIsSyncing(true);
    setSyncElapsed(0);
    setSyncStage(1);

    const controller = new AbortController();
    syncAbortControllerRef.current = controller;

    const timeoutWatchdog = setTimeout(() => {
      if (isSyncingRef.current) {
        controller.abort();
        toast.error('Sync timed out after 35 seconds. Please try again.');
        isSyncingRef.current = false;
        setIsSyncing(false);
        if (syncTimerRef.current) clearInterval(syncTimerRef.current);
      }
    }, 35000);

    syncTimerRef.current = setInterval(() => {
      setSyncElapsed((prev) => {
        const next = prev + 1;
        if (next < 7) {
          setSyncStage(1);
        } else if (next < 17) {
          setSyncStage(2);
        } else {
          setSyncStage(3);
        }
        return next;
      });
    }, 1000);

    try {
      const res = await fetchWithAuth('/api/elein/inbox/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: activeAccountId }),
        signal: controller.signal,
      });

      clearTimeout(timeoutWatchdog);

      if (res.ok) {
        toast.success('Inbox sync complete! Latest threads updated.');
        mutateThreads();
      } else {
        const err = await res.json().catch(() => ({}));
        if (
          err.detail?.toLowerCase().includes('session') ||
          err.detail?.toLowerCase().includes('cookie')
        ) {
          toast.error('LinkedIn Session Expired: Please reconnect your session in Accounts.');
        } else {
          toast.error(err.detail || 'Inbox sync failed.');
        }
      }
    } catch (error: any) {
      clearTimeout(timeoutWatchdog);
      if (error?.name === 'AbortError') return;
      toast.error('Error connecting to sync engine: ' + (error?.message || 'Network drop'));
    } finally {
      if (syncTimerRef.current) {
        clearInterval(syncTimerRef.current);
        syncTimerRef.current = null;
      }
      syncAbortControllerRef.current = null;
      isSyncingRef.current = false;
      setIsSyncing(false);
    }
  };

  // ── Thread Switching with Draft Memory ──
  const handleSelectThread = useCallback(
    (thread: ThreadSummary) => {
      if (isDraftingRef.current && abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
        isDraftingRef.current = false;
        setIsDraftingAI(false);
      }

      if (selectedThreadKey && replyText.trim()) {
        draftsByThreadRef.current[selectedThreadKey] = replyText;
      } else if (selectedThreadKey) {
        delete draftsByThreadRef.current[selectedThreadKey];
      }

      setSelectedThreadKey(thread.thread_key);
      setSelectedSender(thread.sender_name);
      setSelectedLeadId(thread.lead_id || null);

      const cachedDraft = draftsByThreadRef.current[thread.thread_key] || '';
      setReplyText(cachedDraft);
      setSavedDraftBeforeAI(null);
      previousDraftRef.current = '';
      setActiveAIIntent(null);
    },
    [selectedThreadKey, replyText]
  );

  // ── Send Reply with Paranoia Safeguards & 4s Undo ──
  const hasTemplateVars = /\{\{[a-zA-Z0-9_]+\}\}/.test(replyText);

  const handleSend = () => {
    if (!replyText.trim() || isSendingRef.current || !selectedSender) return;

    if (hasTemplateVars) {
      setIsVariableModalOpen(true);
      return;
    }

    triggerSendQueue(replyText.trim());
  };

  const triggerSendQueue = (finalText: string) => {
    if (!selectedSender) return;

    const currentSender = selectedSender;
    const currentLead = selectedLeadId;
    const currentThread = selectedThreadKey;
    const currentAccountId = selectedThreadObj?.account_id || activeAccountId || undefined;

    // Clear textarea immediately for responsive feel
    setReplyText('');
    setSavedDraftBeforeAI(null);
    previousDraftRef.current = '';
    if (currentThread) {
      delete draftsByThreadRef.current[currentThread];
    }

    queueSend(
      {
        senderName: currentSender,
        leadId: currentLead,
        messageText: finalText,
      },
      async () => {
        await executeActualSend(finalText, currentSender, currentLead, currentAccountId);
      },
      (restoredText) => {
        // On Undo Send
        setReplyText(restoredText);
        if (currentThread) {
          draftsByThreadRef.current[currentThread] = restoredText;
        }
      }
    );
  };

  const executeActualSend = async (
    sentDraft: string,
    senderName: string,
    leadId: string | null,
    targetAccountId?: string
  ) => {
    isSendingRef.current = true;
    setIsSending(true);

    try {
      const res = await fetchWithAuth('/api/elein/inbox/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender_name: senderName,
          lead_id: leadId,
          message_text: sentDraft,
          account_id: targetAccountId || activeAccountId || undefined,
        }),
      });

      if (res.ok) {
        toast.success('Reply queued and sent successfully!');
        mutateMessages();
        mutateThreads();
        invalidateCreditBalances();
      } else {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Server rejected reply');
      }
    } catch (error: any) {
      toast.error(error?.message || 'Failed to send reply. Draft restored.');
      setReplyText(sentDraft);
    } finally {
      isSendingRef.current = false;
      setIsSending(false);
    }
  };

  // ── AI Ghostwriter Streaming ──
  const handleSparklesClick = async (customIntent: string = 'unknown') => {
    const sender = selectedSender;
    if (!sender || isDraftingRef.current || isSending) return;

    if (replyText.trim()) {
      previousDraftRef.current = replyText;
      setSavedDraftBeforeAI(replyText);
    } else {
      previousDraftRef.current = '';
      setSavedDraftBeforeAI(null);
    }

    isDraftingRef.current = true;
    setIsDraftingAI(true);
    setActiveAIIntent(customIntent);
    setReplyText('');

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let streamInitiated = false;

    try {
      const thread_messages = (messages || []).map((m) => ({
        sender_name: m.direction === 'outbound' ? 'You' : selectedSender,
        message_text: m.message_text,
        direction: m.direction,
        created_at: m.created_at,
        lead_id: selectedLeadId,
        account_id: activeAccountId,
      }));

      const res = await fetchWithAuth('/api/elein/inbox/ai-suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender_name: selectedSender,
          thread_messages,
          intent: customIntent,
          lead_profile: {
            id: selectedLeadId,
            name: selectedSender,
          },
          campaign_context: '',
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openTopUp({ featureName: 'AI Ghostwriter', neededCredits: 50 });
          if (previousDraftRef.current) setReplyText(previousDraftRef.current);
          invalidateCreditBalances();
          return;
        }
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server error (${res.status})`);
      }

      streamInitiated = true;
      const reader = res.body?.getReader();
      if (!reader) throw new Error('Unable to establish stream reader');

      const decoder = new TextDecoder();
      let accumulated = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });

        if (chunk.includes('insufficient_credits')) {
          controller.abort();
          openTopUp({ featureName: 'AI Ghostwriter', neededCredits: 50 });
          if (previousDraftRef.current) setReplyText(previousDraftRef.current);
          invalidateCreditBalances();
          return;
        }

        accumulated += chunk;
        setReplyText(accumulated.trimStart());
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') return;
      toast.error(error?.message || 'Failed to draft AI response. Draft restored.');
      if (previousDraftRef.current) setReplyText(previousDraftRef.current);
    } finally {
      if (streamInitiated) {
        invalidateCreditBalances();
      }
      isDraftingRef.current = false;
      setIsDraftingAI(false);
      setActiveAIIntent(null);
      abortControllerRef.current = null;
    }
  };

  const handleStopDrafting = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    isDraftingRef.current = false;
    setIsDraftingAI(false);
    setActiveAIIntent(null);
    invalidateCreditBalances();
    toast.info('AI draft generation stopped');
  };

  // ── Deal Pipeline & Battlecard Logic ──
  const currentLeadKey = selectedLeadId || selectedSender || 'unknown';

  const currentDealStage: DealStage = useMemo(() => {
    if (dealStagesByLead[currentLeadKey]) {
      return dealStagesByLead[currentLeadKey];
    }
    const matchedThread = safeThreads.find((t) => t.thread_key === selectedThreadKey);
    return (matchedThread?.deal_stage as DealStage) || 'NEW_REPLY';
  }, [dealStagesByLead, currentLeadKey, safeThreads, selectedThreadKey]);

  const activeObjection: ObjectionData | null = useMemo(() => {
    const matchedThread = safeThreads.find((t) => t.thread_key === selectedThreadKey);
    return matchedThread?.objection_data || null;
  }, [safeThreads, selectedThreadKey]);

  const handleUpdateDealStage = async (newStage: DealStage) => {
    if (!isPro && newStage !== 'NEW_REPLY') {
      openPaywall({
        featureName: 'Deal Pipeline Progression',
        description:
          'Moving leads through advanced pipeline stages requires a Pro or Enterprise subscription.',
        minTier: 'PRO',
      });
      return;
    }

    setDealStagesByLead((prev) => ({ ...prev, [currentLeadKey]: newStage }));

    if (!selectedLeadId) {
      toast.success(`Deal Stage updated to ${DEAL_STAGES[newStage].label}`);
      return;
    }

    try {
      const res = await fetchWithAuth(
        `/api/elein/inbox/threads/${encodeURIComponent(selectedLeadId)}/deal-stage`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            deal_stage: newStage,
            force_override: true,
          }),
        }
      );

      if (res.ok) {
        toast.success(`Deal Stage: ${DEAL_STAGES[newStage].label}`);
        mutateThreads();
      } else {
        toast.error('Failed to update deal stage on server');
      }
    } catch (e: any) {
      toast.error('Network error updating deal stage: ' + (e?.message || ''));
    }
  };

  const handleApplyBattlecardTone = async (
    tone: 'challenger' | 'consultative' | 'casual'
  ) => {
    if (!activeObjection || isGeneratingBattlecard || isSending) return;

    if (!isPro) {
      openPaywall({
        featureName: 'Elesium Objection Battlecards',
        description:
          'Counter pricing, competitor, and timing objections with Challenger, Consultative, and Casual counter-pitches.',
        minTier: 'PRO',
      });
      return;
    }

    if (replyText.trim()) {
      setSavedDraftBeforeAI(replyText);
      previousDraftRef.current = replyText;
    }

    setIsGeneratingBattlecard(true);
    setActiveBattlecardTone(tone);

    try {
      const res = await fetchWithAuth('/api/elein/inbox/battlecard/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          objection_type: activeObjection.objection_type,
          lead_id: selectedLeadId || undefined,
          lead_name: selectedSender || undefined,
          detected_competitor: activeObjection.detected_competitor || undefined,
          detected_timing: activeObjection.detected_timing || undefined,
          detected_referral: activeObjection.detected_referral || undefined,
        }),
      });

      if (!res.ok) throw new Error('Failed to generate battlecard responses');

      const json = await res.json();
      const responses = json.data?.responses || {};
      const pitch = responses[tone];

      if (pitch) {
        const words = pitch.split(' ');
        let accumulated = '';
        setReplyText('');
        for (let i = 0; i < words.length; i++) {
          accumulated += (i > 0 ? ' ' : '') + words[i];
          setReplyText(accumulated);
          await new Promise((r) => setTimeout(r, 16));
        }
        if (currentDealStage === 'NEW_REPLY' || currentDealStage === 'OBJECTION_RAISED') {
          handleUpdateDealStage('BATTLECARD_ENGAGED');
        }
        invalidateCreditBalances();
        toast.success(`Generated ${tone.toUpperCase()} counter-pitch!`);
      }
    } catch (err: any) {
      toast.error(err?.message || 'Failed to load battlecard counter-pitch');
      if (previousDraftRef.current) setReplyText(previousDraftRef.current);
    } finally {
      setIsGeneratingBattlecard(false);
      setActiveBattlecardTone(null);
    }
  };

  // ── Suggested Meeting Slots Insertion ──
  const handleInsertTimeSlotsDirect = (slotsText: string) => {
    setReplyText((prev) => {
      if (!prev.trim()) return slotsText;
      return `${prev.trim()}\n\n${slotsText}`;
    });
    handleUpdateDealStage('MEETING_PROPOSED');
    toast.success('Inserted localized meeting slots into draft!');
  };

  // ── Filtered Threads Memo ──
  const filteredThreads = useMemo(() => {
    return safeThreads.filter((t) => {
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = t.sender_name.toLowerCase().includes(query);
        const matchesMsg = t.last_message.toLowerCase().includes(query);
        if (!matchesName && !matchesMsg) return false;
      }

      if (outcomeFilter !== 'ALL') {
        if (outcomeFilter === 'INBOUND' && t.direction !== 'inbound') return false;
        if (outcomeFilter !== 'INBOUND') {
          const threadOutcome = threadOutcomes[t.thread_key];
          if (threadOutcome !== outcomeFilter) return false;
        }
      }

      if (dealStageFilter !== 'ALL') {
        const stage =
          (dealStagesByLead[t.lead_id || t.thread_key] as DealStage) ||
          (t.deal_stage as DealStage) ||
          'NEW_REPLY';
        if (stage !== dealStageFilter) return false;
      }

      return true;
    });
  }, [
    safeThreads,
    searchQuery,
    outcomeFilter,
    dealStageFilter,
    threadOutcomes,
    dealStagesByLead,
  ]);

  // Counts for filter pills
  const counts = useMemo(() => {
    const res: Record<string, number> = {
      ALL: safeThreads.length,
      INBOUND: safeThreads.filter((t) => t.direction === 'inbound').length,
      INTERESTED: 0,
      MEETING_BOOKED: 0,
      FOLLOW_UP: 0,
      INFO_SENT: 0,
      NOT_INTERESTED: 0,
    };

    safeThreads.forEach((t) => {
      const oc = threadOutcomes[t.thread_key];
      if (oc && res[oc] !== undefined) res[oc]++;
    });

    return res;
  }, [safeThreads, threadOutcomes]);

  const dealStageCounts = useMemo(() => {
    const res: Record<string, number> = {
      ALL: safeThreads.length,
    };
    (Object.keys(DEAL_STAGES) as DealStage[]).forEach((st) => {
      res[st] = 0;
    });
    safeThreads.forEach((t) => {
      const stage =
        (dealStagesByLead[t.lead_id || t.thread_key] as DealStage) ||
        (t.deal_stage as DealStage) ||
        'NEW_REPLY';
      if (res[stage] !== undefined) res[stage]++;
    });
    return res;
  }, [safeThreads, dealStagesByLead]);

  const safeMessages = useMemo<Message[]>(() => {
    return Array.isArray(messages) ? messages : [];
  }, [messages]);

  const activeThreadOutcome = selectedThreadKey
    ? threadOutcomes[selectedThreadKey] || null
    : null;

  const handleToggleOutcome = (key: OutcomeType) => {
    if (selectedThreadKey) {
      handleSetOutcome(selectedThreadKey, activeThreadOutcome === key ? null : key);
    }
  };

  const selectedThreadObj = useMemo(() => {
    return filteredThreads.find((t) => t.thread_key === selectedThreadKey) || null;
  }, [filteredThreads, selectedThreadKey]);

  // Keyboard navigation shortcuts
  useInboxKeyboardShortcuts({
    onNextThread: () => {
      if (filteredThreads.length === 0) return;
      const currentIndex = filteredThreads.findIndex(
        (t) => t.thread_key === selectedThreadKey
      );
      const nextIndex = (currentIndex + 1) % filteredThreads.length;
      handleSelectThread(filteredThreads[nextIndex]);
    },
    onPrevThread: () => {
      if (filteredThreads.length === 0) return;
      const currentIndex = filteredThreads.findIndex(
        (t) => t.thread_key === selectedThreadKey
      );
      const prevIndex =
        (currentIndex - 1 + filteredThreads.length) % filteredThreads.length;
      handleSelectThread(filteredThreads[prevIndex]);
    },
    onFocusComposer: () => {
      composerTextareaRef.current?.focus();
    },
    onToggleInspector: () => {
      setIsInspectorOpen((prev) => !prev);
    },
    onOpenCommandPalette: () => {
      setIsCommandPaletteOpen(true);
    },
    onSnoozeThread: () => {
      if (selectedThreadObj?.objection_data?.detected_timing) {
        handleUpdateDealStage('DISQUALIFIED');
        setReplyText('Following up per our previous conversation timing.');
        toast.success(`Follow-up scheduled for ${selectedThreadObj.objection_data.detected_timing}. Draft check-in prepared.`);
      } else {
        toast.info('No timing objection detected on this thread to auto-snooze.');
      }
    },
    onArchiveThread: () => {
      handleUpdateDealStage('CLOSED_WON');
      toast.success('Deal stage advanced to Closed Won.');
    },
  });

  if (threads !== undefined && safeThreads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-background text-foreground">
        <div className="flex flex-col items-center justify-center text-center p-10 max-w-md bg-card border border-border rounded-xl shadow-sm">
          <div className="w-16 h-16 rounded-xl bg-primary/10 flex items-center justify-center mb-6 border border-primary/20">
            <MessageSquare size={32} className="text-primary" />
          </div>
          <h2 className="text-xl font-bold mb-2">Your inbox is quiet right now</h2>
          <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
            When prospects reply to your outreach campaigns, their messages will appear here. The AI will analyze each reply and suggest the perfect response.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 w-full justify-center">
            <button 
              type="button"
              onClick={handleSync}
              disabled={isSyncing}
              className="flex items-center justify-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold rounded-lg transition-colors border border-primary/20 cursor-pointer shadow-xs"
            >
              <RefreshCw size={14} className={isSyncing ? "animate-spin" : ""} />
              <span>Sync Inbox</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-background text-foreground select-none">
      {/* ── Modern Pill-Segmented Sub-Nav ─────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card shrink-0 select-none">
        <div className="bg-muted p-0.5 rounded-lg border border-border inline-flex items-center gap-1">
          <button
            onClick={() => setActiveTab('messages')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'messages'
                ? 'bg-card text-foreground font-semibold shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <MessageSquare size={13} />
            <span>Conversations</span>
          </button>
          <button
            onClick={() => setActiveTab('approvals')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'approvals'
                ? 'bg-card text-foreground font-semibold shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <ElesiumLogo size={14} />
            <span>AI Approvals</span>
            {(approvalCount?.count ?? 0) > 0 && (
              <span className="ml-1 bg-primary text-primary-foreground text-xs font-bold rounded-full px-1.5 py-0.2 leading-none">
                {approvalCount!.count}
              </span>
            )}
          </button>
        </div>

        {/* Sub-nav right actions / clean padding */}
        <div />
      </div>

      {/* ── Main Workspace Body ───────────────────────────────────── */}
      {activeTab === 'approvals' ? (
        <div className="flex-1 overflow-auto p-4 bg-background">
          <EleInApprovals onGoToConversations={() => setActiveTab('messages')} />
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* 1. Left Rail: Thread List Pane (Resizable) */}
          <div
            style={{ width: `${threadListWidth}px` }}
            className={`${
              selectedSender ? 'hidden md:flex' : 'flex w-full'
            } shrink-0 flex-col h-full min-h-0 [&>div]:w-full [&>div]:max-w-full [&>div]:h-full [&>div]:border-r-0`}
          >
            <ThreadListPane
              threads={filteredThreads}
              selectedThreadKey={selectedThreadKey}
              onSelectThread={handleSelectThread}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              outcomeFilter={outcomeFilter}
              onOutcomeFilterChange={setOutcomeFilter}
              dealStageFilter={dealStageFilter}
              onDealStageFilterChange={setDealStageFilter}
              counts={counts}
              dealStageCounts={dealStageCounts}
              threadOutcomes={threadOutcomes}
              dealStagesByLead={dealStagesByLead}
              draftsByThread={draftsByThreadRef.current}
              isSyncing={isSyncing}
              syncStage={syncStage}
              syncElapsed={syncElapsed}
              onSync={handleSync}
              onCancelSync={handleCancelSync}
              accounts={accounts}
              activeAccountId={activeAccountId}
              onAccountChange={setSelectedAccountId}
              onConnectAccount={() => navigate('/elein/accounts')}
            />
          </div>

          {/* Draggable Resizer Line (Linear / Superhuman Splitter) */}
          <div
            onMouseDown={handleMouseDownResize}
            className="hidden md:flex w-1 hover:w-1.5 active:w-1.5 bg-border hover:bg-primary/50 active:bg-primary cursor-col-resize shrink-0 transition-[width,background-color] relative z-20 group items-center justify-center select-none"
            title="Drag to resize thread list"
          >
            <div className="w-0.5 h-8 rounded-full bg-muted-foreground/30 group-hover:bg-primary/80 transition-colors" />
          </div>

          {/* 2. Center Canvas: Conversation & Composer */}
          <div
            className={`${
              selectedSender ? 'flex w-full' : 'hidden md:flex'
            } flex-1 flex-col bg-background overflow-hidden min-w-0 h-full`}
          >
            <ConversationCanvas
              selectedSender={selectedSender}
              selectedLeadId={selectedLeadId}
              selectedThread={selectedThreadObj}
              messages={safeMessages}
              currentDealStage={currentDealStage}
              onUpdateDealStage={handleUpdateDealStage}
              isInspectorOpen={isInspectorOpen}
              onToggleInspector={() => setIsInspectorOpen((prev) => !prev)}
              onBack={() => {
                setSelectedThreadKey(null);
                setSelectedSender(null);
                setSelectedLeadId(null);
              }}
              onSnoozeToDate={(dateText, checkInText) => {
                handleUpdateDealStage('DISQUALIFIED'); // Or advance stage
                setReplyText(checkInText);
                if (selectedThreadKey) {
                  draftsByThreadRef.current[selectedThreadKey] = checkInText;
                }
                toast.success(`Follow-up scheduled for ${dateText}. Draft check-in prepared.`);
              }}
            />

            {selectedSender && (
              <ComposerStation
                textareaRef={composerTextareaRef}
                replyText={replyText}
                onReplyTextChange={(val) => {
                  setReplyText(val);
                  if (selectedThreadKey) {
                    draftsByThreadRef.current[selectedThreadKey] = val;
                  }
                }}
                onSend={handleSend}
                isSending={isSending}
                isDraftingAI={isDraftingAI}
                activeAIIntent={activeAIIntent}
                onTriggerGhostwriter={handleSparklesClick}
                onStopDrafting={handleStopDrafting}
                savedDraftBeforeAI={savedDraftBeforeAI}
                onRestoreDraft={() => {
                  if (savedDraftBeforeAI) {
                    setReplyText(savedDraftBeforeAI);
                    setSavedDraftBeforeAI(null);
                    previousDraftRef.current = '';
                    toast.info('Original draft restored');
                  }
                }}
                hasTemplateVars={hasTemplateVars}
                activeObjection={activeObjection}
                activeBattlecardTone={activeBattlecardTone}
                isGeneratingBattlecard={isGeneratingBattlecard}
                onApplyBattlecardTone={handleApplyBattlecardTone}
                onOpenSlotPicker={() => setIsSlotPickerOpen(true)}
                isInsertingSlots={isInsertingSlots}
                sendOnEnter={sendOnEnter}
                onSendOnEnterChange={setSendOnEnter}
              />
            )}
          </div>

          {/* 3. Right Rail: Intelligence Inspector */}
          {selectedSender && (
            <IntelligenceInspector
              isOpen={isInspectorOpen}
              onClose={() => setIsInspectorOpen(false)}
              selectedSender={selectedSender}
              selectedLeadId={selectedLeadId}
              selectedThread={selectedThreadObj}
              currentDealStage={currentDealStage}
              onUpdateDealStage={handleUpdateDealStage}
              activeObjection={activeObjection}
              activeThreadOutcome={activeThreadOutcome}
              onToggleOutcome={handleToggleOutcome}
              onInsertPivotAngle={(pivot) => {
                setReplyText((prev) => (prev ? `${prev}\n\n${pivot}` : pivot));
                toast.success('Inserted pivot angle into composer!');
              }}
            />
          )}
        </div>
      )}

      {/* Modals & Command Palette */}
      <InboxCommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onDeployBattlecard={handleApplyBattlecardTone}
        onAdvanceDealStage={handleUpdateDealStage}
        onInsertSlots={() => setIsSlotPickerOpen(true)}
        onTriggerGhostwriter={() => handleSparklesClick('unknown')}
        onSync={handleSync}
        onToggleInspector={() => setIsInspectorOpen((prev) => !prev)}
      />

      <VariableFillModal
        isOpen={isVariableModalOpen}
        onClose={() => setIsVariableModalOpen(false)}
        text={replyText}
        onApplyAndSend={(resolvedText) => {
          setIsVariableModalOpen(false);
          triggerSendQueue(resolvedText);
        }}
        defaultValues={{
          first_name: selectedSender ? selectedSender.split(' ')[0] : '',
          name: selectedSender || '',
          company: selectedThreadObj?.company || '',
        }}
      />

      <TimezoneSlotPickerModal
        isOpen={isSlotPickerOpen}
        onClose={() => setIsSlotPickerOpen(false)}
        leadName={selectedSender || 'Prospect'}
        leadTimezone={selectedThreadObj?.lead_timezone || 'EDT'}
        onInsertSlots={handleInsertTimeSlotsDirect}
      />
    </div>
  );
}
