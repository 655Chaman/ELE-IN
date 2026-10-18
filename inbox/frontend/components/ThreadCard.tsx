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
      onClick={onSelect}
      className={`mx-2 my-1 p-3 rounded-xl cursor-pointer transition-all duration-150 relative border ${
        isSelected
          ? 'bg-primary/10 border-primary/30 dark:bg-accent/70 dark:border-border shadow-xs'
          : 'border-transparent hover:bg-muted/70 hover:border-border/60'
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs shrink-0 mt-0.5 bg-muted text-foreground border border-border">
          {thread.sender_name
            ? thread.sender_name.slice(0, 2).toUpperCase()
            : 'LE'}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Line 1: Name + Date (Clean, never crowded) */}
          <div className="flex justify-between items-baseline gap-2 mb-0.5">
            <span className="text-sm font-semibold text-foreground truncate">
              {thread.sender_name}
            </span>

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
          <div className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
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
