import { useState } from 'react';
import {
  Check, ChevronDown, Filter, Gamepad2, RefreshCw, Search, X
} from 'lucide-react';
import { ThreadCard } from './ThreadCard';
import { DEAL_STAGES, OUTCOMES, type DealStage, type OutcomeType, type ThreadSummary } from '../types';
import { SIMULATED_SCENARIOS } from '../inboxPlaygroundData';

interface ThreadListPaneProps {
  threads: ThreadSummary[];
  selectedThreadKey: string | null;
  onSelectThread: (thread: ThreadSummary) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  outcomeFilter: 'ALL' | 'INBOUND' | OutcomeType;
  onOutcomeFilterChange: (f: 'ALL' | 'INBOUND' | OutcomeType) => void;
  dealStageFilter: 'ALL' | DealStage;
  onDealStageFilterChange: (f: 'ALL' | DealStage) => void;
  counts: Record<string, number>;
  dealStageCounts: Record<string, number>;
  threadOutcomes: Record<string, OutcomeType>;
  dealStagesByLead: Record<string, DealStage>;
  draftsByThread: Record<string, string>;
  isPlaygroundActive: boolean;
  onToggleSimulator: () => void;
  isSyncing: boolean;
  syncStage: 1 | 2 | 3;
  syncElapsed: number;
  onSync: () => void;
  onCancelSync: () => void;
  accounts: any[];
  activeAccountId: string;
  onAccountChange: (accId: string) => void;
  onConnectAccount: () => void;
}

export function ThreadListPane({
  threads,
  selectedThreadKey,
  onSelectThread,
  searchQuery,
  onSearchChange,
  outcomeFilter,
  onOutcomeFilterChange,
  dealStageFilter,
  onDealStageFilterChange,
  counts,
  dealStageCounts,
  threadOutcomes,
  dealStagesByLead,
  draftsByThread,
  isPlaygroundActive,
  onToggleSimulator,
  isSyncing,
  syncStage,
  syncElapsed,
  onSync,
  onCancelSync,
  accounts,
  activeAccountId,
  onAccountChange,
  onConnectAccount,
}: ThreadListPaneProps) {
  const [isFilterMenuOpen, setIsFilterMenuOpen] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);

  const activeAccount = accounts.find((a: any) => a.id === activeAccountId) || accounts[0];

  return (
    <div className="w-full h-full flex flex-col bg-card shrink-0 select-none">
      {/* Top Header & Search Area */}
      <div className="p-3 border-b border-border bg-card sticky top-0 flex flex-col gap-2 z-10">
        {/* Top row: Clean Title + Mode/Sync Action */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <h2 className="text-sm font-semibold text-foreground truncate">
              {isPlaygroundActive ? 'Sample Inbox' : 'Inbox'}
            </h2>
            <span className="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border shrink-0">
              {threads.length}
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Show account switcher only when live accounts exist */}
            {accounts.length > 1 ? (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setIsAccountMenuOpen(!isAccountMenuOpen)}
                  className="bg-muted hover:bg-muted/80 text-foreground px-2.5 py-1 rounded-md border border-border text-xs flex items-center justify-between gap-1.5 cursor-pointer max-w-32"
                  title={`Active account: ${activeAccount?.name || 'Select account'}`}
                >
                  <span className="truncate">{activeAccount?.name || 'Account'}</span>
                  <ChevronDown size={12} className="shrink-0 text-muted-foreground" />
                </button>

                {isAccountMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-30"
                      onClick={() => setIsAccountMenuOpen(false)}
                    />
                    <div className="absolute right-0 top-full mt-1.5 z-40 min-w-44 bg-popover text-popover-foreground border border-border shadow-lg rounded-xl p-1">
                      <div className="text-xs uppercase font-bold text-muted-foreground px-2 py-1">
                        Sender Account
                      </div>
                      {accounts.map((acc: any) => (
                        <button
                          key={acc.id}
                          type="button"
                          onClick={() => {
                            onAccountChange(acc.id);
                            setIsAccountMenuOpen(false);
                          }}
                          className={`w-full text-left px-2 py-1.5 rounded-md text-xs flex items-center justify-between gap-2 cursor-pointer transition-colors ${
                            acc.id === activeAccountId
                              ? 'bg-accent text-accent-foreground font-semibold'
                              : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                          }`}
                        >
                          <span className="truncate">{acc.name}</span>
                          {acc.id === activeAccountId && (
                            <Check size={12} className="text-primary shrink-0" />
                          )}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : accounts.length === 0 && !isPlaygroundActive ? (
              <button
                type="button"
                onClick={onConnectAccount}
                className="bg-muted hover:bg-muted/80 text-foreground border border-border px-2.5 py-1 rounded-md text-xs font-medium flex items-center gap-1 cursor-pointer transition-colors"
                title="Connect account"
              >
                <span>Connect</span>
              </button>
            ) : null}

            {accounts.length > 0 && (
              <button
                type="button"
                onClick={onToggleSimulator}
                className={`px-2 py-1 rounded-md border text-xs font-medium flex items-center gap-1 transition-all cursor-pointer ${
                  isPlaygroundActive
                    ? 'bg-primary text-primary-foreground border-primary font-semibold'
                    : 'bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground border-border'
                }`}
                title={isPlaygroundActive ? 'Switch back to live inbox' : 'Practice with sample leads'}
              >
                <Gamepad2 size={12} />
                <span>{isPlaygroundActive ? 'Demo On' : 'Demo'}</span>
              </button>
            )}

            <button
              type="button"
              onClick={onSync}
              disabled={isSyncing}
              className="p-1.5 bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground border border-border rounded-md transition-colors disabled:opacity-50 cursor-pointer"
              title="Sync latest LinkedIn messages"
              aria-label="Sync latest LinkedIn messages"
            >
              <RefreshCw size={13} className={isSyncing ? 'animate-spin text-primary' : ''} />
            </button>
          </div>
        </div>

        {/* Second row: Search bar with clear button (X) */}
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search prospect or message..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full bg-background border border-border rounded-md pl-8 pr-7 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => onSearchChange('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              title="Clear search"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Third row: Segmented filter row & Advanced Filters popover */}
        <div className="flex items-center justify-between gap-1.5 text-xs">
          <div className="flex items-center bg-muted p-0.5 rounded-lg border border-border flex-1">
            <button
              type="button"
              onClick={() => {
                onOutcomeFilterChange('ALL');
                onDealStageFilterChange('ALL');
              }}
              className={`flex-1 py-1 text-center rounded-md text-xs font-medium transition-all cursor-pointer ${
                outcomeFilter === 'ALL' && dealStageFilter === 'ALL'
                  ? 'bg-card text-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              All ({counts.ALL ?? 0})
            </button>
            <button
              type="button"
              onClick={() => onOutcomeFilterChange('INBOUND')}
              className={`flex-1 py-1 text-center rounded-md text-xs font-medium transition-all cursor-pointer ${
                outcomeFilter === 'INBOUND'
                  ? 'bg-card text-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Replies ({counts.INBOUND ?? 0})
            </button>
            <button
              type="button"
              onClick={() => onOutcomeFilterChange('MEETING_BOOKED')}
              className={`flex-1 py-1 text-center rounded-md text-xs font-medium transition-all cursor-pointer ${
                outcomeFilter === 'MEETING_BOOKED'
                  ? 'bg-card text-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Booked ({counts.MEETING_BOOKED ?? 0})
            </button>
          </div>

          {/* Advanced Filter Popover */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsFilterMenuOpen(!isFilterMenuOpen)}
              className={`p-1.5 rounded-md border text-xs flex items-center gap-1 transition-all cursor-pointer ${
                dealStageFilter !== 'ALL' ||
                (outcomeFilter !== 'ALL' &&
                  outcomeFilter !== 'INBOUND' &&
                  outcomeFilter !== 'MEETING_BOOKED')
                  ? 'bg-primary text-primary-foreground border-primary font-semibold'
                  : 'bg-muted hover:bg-muted/80 border-border text-muted-foreground hover:text-foreground'
              }`}
              title="Filter by Deal Stage or Outcome Tag"
            >
              <Filter size={13} />
              {dealStageFilter !== 'ALL' && (
                <span className="w-1.5 h-1.5 rounded-full bg-primary-foreground" />
              )}
            </button>

            {isFilterMenuOpen && (
              <>
                <div
                  className="fixed inset-0 z-30"
                  onClick={() => setIsFilterMenuOpen(false)}
                />
                <div className="absolute right-0 top-full mt-1.5 z-40 w-56 rounded-xl bg-popover text-popover-foreground border border-border shadow-2xl p-2 space-y-2 animate-in fade-in duration-150">
                  <div>
                    <div className="text-xs uppercase font-bold text-muted-foreground px-1 mb-1">
                      Deal Stage
                    </div>
                    <div className="space-y-0.5 max-h-44 overflow-y-auto">
                      <button
                        type="button"
                        onClick={() => {
                          onDealStageFilterChange('ALL');
                          setIsFilterMenuOpen(false);
                        }}
                        className={`w-full text-left px-2 py-1 rounded-md text-xs flex items-center justify-between cursor-pointer ${
                          dealStageFilter === 'ALL'
                            ? 'bg-accent text-accent-foreground font-medium'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                        }`}
                      >
                        <span>All Stages</span>
                        {dealStageFilter === 'ALL' && (
                          <Check size={11} className="text-primary" />
                        )}
                      </button>
                      {(Object.keys(DEAL_STAGES) as DealStage[]).map((st) => (
                        <button
                          key={st}
                          type="button"
                          onClick={() => {
                            onDealStageFilterChange(st);
                            setIsFilterMenuOpen(false);
                          }}
                          className={`w-full text-left px-2 py-1 rounded-md text-xs flex items-center justify-between cursor-pointer ${
                            dealStageFilter === st
                              ? 'bg-accent text-accent-foreground font-medium'
                              : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                          }`}
                        >
                          <span className="truncate">{DEAL_STAGES[st].label}</span>
                          <span className="text-xs text-muted-foreground/75 font-medium">
                            ({dealStageCounts[st] || 0})
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="pt-1.5 border-t border-border">
                    <div className="text-xs uppercase font-bold text-muted-foreground px-1 mb-1">
                      Outcome Tag
                    </div>
                    <div className="space-y-0.5">
                      {(
                        ['INTERESTED', 'FOLLOW_UP', 'INFO_SENT', 'NOT_INTERESTED'] as OutcomeType[]
                      ).map((oc) => (
                        <button
                          key={oc}
                          type="button"
                          onClick={() => {
                            onOutcomeFilterChange(oc);
                            setIsFilterMenuOpen(false);
                          }}
                          className={`w-full text-left px-2 py-1 rounded-md text-xs flex items-center justify-between cursor-pointer ${
                            outcomeFilter === oc
                              ? 'bg-accent text-accent-foreground font-medium'
                              : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                          }`}
                        >
                          <span>{OUTCOMES[oc].label}</span>
                          <span className="text-xs text-muted-foreground/75 font-medium">
                            ({counts[oc] || 0})
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Playwright Sync Live Dock */}
      {isSyncing && (
        <div className="m-3 p-3 bg-muted/60 border border-border rounded-xl animate-in fade-in duration-200">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <RefreshCw size={12} className="animate-spin text-primary" />
              <span>Syncing with LinkedIn</span>
            </span>
            <span className="text-xs text-muted-foreground font-medium">
              {String(Math.floor(syncElapsed / 60)).padStart(2, '0')}:
              {String(syncElapsed % 60).padStart(2, '0')} / ~00:25
            </span>
          </div>

          <div className="w-full bg-background h-1.5 rounded-full overflow-hidden mb-2">
            <div
              className="bg-primary h-full transition-all duration-500 rounded-full"
              style={{
                width: `${Math.min(94, Math.max(15, (syncElapsed / 25) * 100))}%`,
              }}
            />
          </div>

          <div className="space-y-1 text-xs text-muted-foreground">
            <div className={syncStage >= 1 ? 'text-foreground font-medium' : ''}>
              [1/3] Session Authentication &amp; Handshake
            </div>
            <div className={syncStage >= 2 ? 'text-foreground font-medium' : ''}>
              [2/3] Extracting Message Streams &amp; DMs
            </div>
            <div className={syncStage >= 3 ? 'text-foreground font-medium' : ''}>
              [3/3] Parsing Sentiment &amp; Responses
            </div>
          </div>

          <div className="mt-2 pt-1.5 border-t border-border flex justify-end">
            <button
              type="button"
              onClick={onCancelSync}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 cursor-pointer"
            >
              <X size={11} />
              <span>Cancel Sync</span>
            </button>
          </div>
        </div>
      )}

      {/* Thread List Items */}
      <div className="flex-1 overflow-y-auto py-1">
        {threads.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-xs space-y-2">
            <p>No conversations match your search or filter.</p>
            {(searchQuery || outcomeFilter !== 'ALL' || dealStageFilter !== 'ALL') && (
              <button
                type="button"
                onClick={() => {
                  onSearchChange('');
                  onOutcomeFilterChange('ALL');
                  onDealStageFilterChange('ALL');
                }}
                className="text-primary text-xs underline font-medium cursor-pointer"
              >
                Clear all filters
              </button>
            )}
          </div>
        ) : (
          threads.map((thread) => {
            const sc = isPlaygroundActive
              ? SIMULATED_SCENARIOS.find((s) => s.threadKey === thread.thread_key)
              : null;
            const outcome = isPlaygroundActive && sc
              ? threadOutcomes[sc.id]
              : threadOutcomes[thread.thread_key];
            const dealStage = isPlaygroundActive && sc
              ? dealStagesByLead[sc.id]
              : dealStagesByLead[thread.lead_id || thread.thread_key] || thread.deal_stage;
            const hasDraft = Boolean(draftsByThread[thread.thread_key]);

            return (
              <ThreadCard
                key={thread.thread_key}
                thread={thread}
                isSelected={selectedThreadKey === thread.thread_key}
                onSelect={() => onSelectThread(thread)}
                outcome={outcome}
                dealStage={dealStage}
                hasDraft={hasDraft}
                simulatedScenario={sc}
              />
            );
          })
        )}
      </div>
    </div>
  );
}
