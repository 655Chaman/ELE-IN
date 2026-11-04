import { UserCheck } from 'lucide-react';
import { DEAL_STAGES, OUTCOMES, type DealStage, type OutcomeType, type ThreadSummary } from '../types';

interface ThreadCardProps {
  thread: ThreadSummary;
  isSelected: boolean;
  onSelect: () => void;
  outcome?: OutcomeType | null;
  dealStage?: DealStage;
  hasDraft?: boolean;
}

export function ThreadCard({
  thread,
  isSelected,
  onSelect,
  outcome,
  dealStage,
  hasDraft,
}: ThreadCardProps) {
  const outcomeConfig = outcome ? OUTCOMES[outcome] : null;
  const stageConfig = dealStage && dealStage !== 'NEW_REPLY' ? DEAL_STAGES[dealStage] : null;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect();
        }
      }}
      className={`mx-2 my-1 p-3 rounded-xl cursor-pointer transition-all duration-150 relative border focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
        isSelected
          ? 'bg-primary/10 border-primary/30 dark:bg-accent/70 dark:border-border shadow-xs'
          : 'border-transparent hover:bg-muted/70 hover:border-border/60'
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Avatar with live unread indicator */}
        <div className="relative shrink-0 mt-0.5">
          <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs bg-muted text-foreground border border-border">
            {thread.sender_name
              ? thread.sender_name.slice(0, 2).toUpperCase()
              : 'LE'}
          </div>
          {(thread.unread_count ?? 0) > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-primary border-2 border-card" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Line 1: Name + Date + Unread Badge (Clean, never crowded) */}
          <div className="flex justify-between items-baseline gap-2 mb-0.5">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className={`text-sm truncate ${(thread.unread_count ?? 0) > 0 ? 'font-bold text-foreground' : 'font-semibold text-foreground/90'}`}>
                {thread.sender_name}
              </span>
              {(thread.unread_count ?? 0) > 0 && (
                <span className="text-[10px] font-semibold bg-primary/15 text-primary border border-primary/25 px-1.5 py-0.5 rounded-full shrink-0">
                  {thread.unread_count}
                </span>
              )}
            </div>

            <span className="text-xs text-muted-foreground shrink-0 font-medium">
              {new Date(thread.created_at).toLocaleDateString([], {
                month: 'short',
                day: 'numeric',
              })}
            </span>
          </div>

          {/* Line 2: Campaign (or company fallback) */}
          <div className="text-xs text-muted-foreground truncate mb-1">
            {thread.campaign_name || thread.company || 'Active Campaign'}
          </div>

          {/* Line 3: Message Preview */}
          <div className={`text-xs line-clamp-2 leading-relaxed ${(thread.unread_count ?? 0) > 0 ? 'font-medium text-foreground' : 'text-muted-foreground'}`}>
            {thread.type === 'connection_accepted' ? (
              <span className="flex items-center gap-1 italic text-primary">
                <UserCheck size={12} className="shrink-0" /> Connection Accepted
              </span>
            ) : (
              <>
                {thread.direction === 'outbound' && (
                  <span className="text-foreground font-medium">You: </span>
                )}
                {thread.last_message}
              </>
            )}
          </div>

          {/* Line 4: Clean Metadata Tags (Anchored at bottom, never crowding name) */}
          {(hasDraft || outcomeConfig || stageConfig) && (
            <div className="flex items-center gap-1.5 mt-2">
              {hasDraft && !isSelected && (
                <span className="text-xs font-medium bg-muted text-muted-foreground border border-border px-1.5 py-0.5 rounded-md">
                  Draft
                </span>
              )}

              {outcomeConfig && (
                <span
                  className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md border ${outcomeConfig.badgeClass}`}
                >
                  <span>{outcomeConfig.label}</span>
                </span>
              )}

              {stageConfig && !outcomeConfig && (
                <span
                  className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-md border ${stageConfig.badgeClass}`}
                >
                  {stageConfig.label}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
