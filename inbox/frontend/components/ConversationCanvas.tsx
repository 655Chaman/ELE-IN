import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, CalendarClock, Check, ChevronDown, Clock,
  MessageSquare, Target,
  UserCheck, X
} from 'lucide-react';
import { ElesiumLogo } from '@/components/ElesiumLogo';
import { DEAL_STAGES, type DealStage, type Message, type ThreadSummary } from '../types';

interface ConversationCanvasProps {
  selectedSender: string | null;
  selectedLeadId: string | null;
  selectedThread: ThreadSummary | null;
  messages: Message[];
  currentDealStage: DealStage;
  onUpdateDealStage: (stage: DealStage) => void;
  isInspectorOpen: boolean;
  onToggleInspector: () => void;
  onBack?: () => void;
  onSnoozeToDate?: (snoozeDateText: string, suggestedCheckIn: string) => void;
}

export function ConversationCanvas({
  selectedSender,
  selectedLeadId: _selectedLeadId,
  selectedThread,
  messages,
  currentDealStage,
  onUpdateDealStage,
  isInspectorOpen,
  onToggleInspector,
  onBack,
  onSnoozeToDate,
}: ConversationCanvasProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isStageDropdownOpen, setIsStageDropdownOpen] = useState(false);
  const [isSnoozeDismissed, setIsSnoozeDismissed] = useState(false);

  useEffect(() => {
    setIsSnoozeDismissed(false);
  }, [selectedSender]);

  // Auto-scroll to bottom of conversation when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  if (!selectedSender) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground p-8 text-center bg-background select-none">
        <div className="w-16 h-16 rounded-xl bg-muted/40 border border-border flex items-center justify-center mb-4">
          <MessageSquare size={32} className="opacity-40 text-primary" />
        </div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Select a Conversation</h3>
        <p className="text-xs text-muted-foreground max-w-xs mb-3">
          Choose a contact on the left to read messages and draft AI replies.
        </p>
      </div>
    );
  }

  const stageCfg = DEAL_STAGES[currentDealStage] || DEAL_STAGES.NEW_REPLY;
  const stageKeys = Object.keys(DEAL_STAGES) as DealStage[];

  return (
    <div className="flex-1 flex flex-col bg-background overflow-hidden">
      {/* Thread Header: Spacious 2-Column Layout */}
      <div className="px-5 py-3 border-b border-border bg-card shrink-0 flex items-center justify-between gap-3 select-none">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="md:hidden p-1.5 -ml-1 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer shrink-0"
              title="Back to Inbox"
              aria-label="Back to Inbox"
            >
              <ArrowLeft size={18} />
            </button>
          )}

          <div className="w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs shrink-0 bg-muted text-foreground border border-border">
            {selectedSender ? selectedSender.slice(0, 2).toUpperCase() : 'LE'}
          </div>

          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-bold text-foreground truncate">
              {selectedSender}
            </h2>

            <div className="flex items-center gap-1.5 text-xs text-muted-foreground truncate">
              <Target size={11} className="text-muted-foreground shrink-0" />
              <span>
                Campaign:{' '}
                <strong className="font-medium text-foreground">
                  {selectedThread?.campaign_name || 'Active Campaign'}
                </strong>
              </span>
            </div>
          </div>
        </div>

        {/* Right actions: 1-Click Stage Selector, Reset (in demo), & AI Coach */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Interactive Stage Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsStageDropdownOpen(!isStageDropdownOpen)}
              className={`px-2.5 py-1.5 rounded-md border text-xs font-medium flex items-center gap-1.5 cursor-pointer transition-colors whitespace-nowrap ${stageCfg.badgeClass}`}
              title="Change Deal Stage"
            >
              <span>{stageCfg.label}</span>
              <ChevronDown size={12} className="opacity-70" />
            </button>

            {isStageDropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-30"
                  onClick={() => setIsStageDropdownOpen(false)}
                />
                <div className="absolute right-0 top-full mt-1.5 z-40 w-48 rounded-xl bg-popover text-popover-foreground border border-border shadow-xl p-1 space-y-0.5">
                  <div className="text-xs font-bold text-muted-foreground px-2 py-1">
                    Pipeline Stage
                  </div>
                  {stageKeys.map((stKey) => {
                    const cfg = DEAL_STAGES[stKey];
                    const isCurrent = currentDealStage === stKey;
                    return (
                      <button
                        key={stKey}
                        type="button"
                        onClick={() => {
                          onUpdateDealStage(stKey);
                          setIsStageDropdownOpen(false);
                        }}
                        className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs flex items-center justify-between cursor-pointer transition-colors ${
                          isCurrent
                            ? 'bg-primary/10 text-primary font-semibold'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                        }`}
                      >
                        <span className="truncate">{cfg.label}</span>
                        {isCurrent && <Check size={12} className="text-primary shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          <button
            type="button"
            onClick={onToggleInspector}
            className={`px-3 py-1.5 rounded-md border text-xs flex items-center gap-1.5 transition-colors cursor-pointer whitespace-nowrap ${
              isInspectorOpen
                ? 'bg-primary text-primary-foreground border-primary font-semibold'
                : 'bg-muted text-muted-foreground hover:text-foreground border-border hover:bg-muted/80'
            }`}
            title="Show/Hide AI Coach & Lead Info (Cmd+I)"
          >
            <ElesiumLogo size={14} />
            <span className="font-semibold">AI Coach</span>
          </button>
        </div>
      </div>

      {/* ── Smart Auto-Snooze & Follow-Up Banner ── */}
      {!isSnoozeDismissed && selectedThread?.objection_data?.detected_timing && (
        <div className="mx-5 mt-3 px-3.5 py-2.5 rounded-xl bg-card border border-border shadow-xs flex items-center justify-between gap-3 text-xs shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-md bg-muted border border-border flex items-center justify-center shrink-0 text-muted-foreground">
              <CalendarClock size={14} />
            </div>
            <div className="min-w-0">
              <div className="font-semibold text-foreground truncate">
                Follow-up requested for {selectedThread.objection_data.detected_timing}
              </div>
              {selectedThread.objection_data.summary && (
                <div className="text-muted-foreground text-xs truncate">
                  {selectedThread.objection_data.summary}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => {
                onSnoozeToDate?.(
                  selectedThread.objection_data!.detected_timing!,
                  'Following up per previous conversation timing'
                );
                setIsSnoozeDismissed(true);
              }}
              className="px-2.5 py-1 rounded-md bg-muted hover:bg-muted/80 text-foreground border border-border font-medium transition-colors cursor-pointer text-xs flex items-center gap-1.5"
              title={`Snooze thread to ${selectedThread.objection_data.detected_timing} and prepare check-in`}
            >
              <Clock size={12} className="text-muted-foreground" />
              <span>Snooze to {selectedThread.objection_data.detected_timing}</span>
            </button>
            <button
              type="button"
              onClick={() => setIsSnoozeDismissed(true)}
              className="p-1 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted transition-colors cursor-pointer"
              title="Dismiss banner"
              aria-label="Dismiss banner"
            >
              <X size={13} />
            </button>
          </div>
        </div>
      )}

      {/* Message History Feed */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-40 text-muted-foreground text-xs">
            No message history recorded for this contact yet.
          </div>
        )}

        {messages.map((msg) => {
          if (msg.type === 'connection_accepted') {
            return (
              <div key={msg.id} className="flex justify-center my-3">
                <div className="px-3.5 py-1 bg-muted border border-border rounded-full flex items-center gap-2 text-xs font-medium text-foreground shadow-2xs">
                  <UserCheck size={13} className="text-primary" />
                  <span>Connection Request Accepted</span>
                  <span className="opacity-50 ml-1.5 text-xs">
                    {new Date(msg.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          }

          const isOutbound = msg.direction === 'outbound';

          return (
            <div
              key={msg.id}
              className={`flex ${isOutbound ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] sm:max-w-xl lg:max-w-2xl rounded-xl p-3.5 shadow-xs ${
                  isOutbound
                    ? 'bg-primary text-primary-foreground dark:bg-primary/20 dark:text-foreground dark:border dark:border-primary/30'
                    : 'bg-card text-foreground border border-border'
                }`}
              >
                <p className="whitespace-pre-wrap text-xs sm:text-sm leading-relaxed">
                  {msg.message_text}
                </p>
                <div
                  className={`mt-1.5 text-xs flex items-center justify-end gap-1 ${
                    isOutbound
                      ? 'text-primary-foreground/75 dark:text-muted-foreground'
                      : 'text-muted-foreground'
                  }`}
                >
                  {new Date(msg.created_at).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
