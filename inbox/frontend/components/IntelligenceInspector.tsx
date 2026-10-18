import { useState } from 'react';
import {
  Check, ChevronDown, Globe, Swords, X, Zap
} from 'lucide-react';
import { ElesiumLogo } from '@/components/ElesiumLogo';
import {
  DEAL_STAGES, OUTCOMES, type DealStage, type ObjectionData, type OutcomeType, type ThreadSummary
} from '../types';

interface IntelligenceInspectorProps {
  isOpen: boolean;
  onClose: () => void;
  selectedSender: string | null;
  selectedLeadId: string | null;
  selectedThread?: ThreadSummary | null;
  currentDealStage: DealStage;
  onUpdateDealStage: (stage: DealStage) => void;
  activeObjection: ObjectionData | null;
  activeThreadOutcome: OutcomeType | null;
  onToggleOutcome: (key: OutcomeType) => void;
  onInsertPivotAngle?: (pivot: string) => void;
}

export function IntelligenceInspector({
  isOpen,
  onClose,
  selectedSender: _selectedSender,
  selectedLeadId: _selectedLeadId,
  selectedThread,
  currentDealStage,
  onUpdateDealStage,
  activeObjection,
  activeThreadOutcome,
  onToggleOutcome,
  onInsertPivotAngle,
}: IntelligenceInspectorProps) {
  const [isStageMenuOpen, setIsStageMenuOpen] = useState(false);

  if (!isOpen) return null;

  const stageKeys = Object.keys(DEAL_STAGES) as DealStage[];
  const currentStageIdx = stageKeys.indexOf(currentDealStage);
  const currentStageCfg = DEAL_STAGES[currentDealStage] || DEAL_STAGES.NEW_REPLY;

  return (
    <>
      {/* Backdrop below 2xl (< 1536px) so drawer never crushes laptop chat width */}
      <div
        className="fixed inset-0 bg-background/60 backdrop-blur-xs z-30 2xl:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <aside className="fixed inset-y-0 right-0 z-40 w-[300px] /* ds-allow-hardcode */ max-w-[85vw] bg-card border-l border-border shadow-2xl 2xl:relative 2xl:z-auto 2xl:shadow-none flex flex-col shrink-0 overflow-y-auto animate-in slide-in-from-right-4 duration-200">
        {/* Header */}
        <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0 bg-card">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={15} />
            <span className="text-xs font-bold text-foreground">AI Deal Coach</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted transition-colors cursor-pointer"
            title="Close panel (Cmd+I)"
          >
            <X size={14} />
          </button>
        </div>

        <div className="p-4 space-y-5 flex-1">
          {/* 1. AI Objection Summary & Strategy (Top Priority, Above the Fold) */}
          {activeObjection ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">Detected Objection</span>
                <span className="text-xs font-semibold text-primary">
                  {Math.round(activeObjection.confidence * 100)}% Match
                </span>
              </div>

              <div className="p-3.5 rounded-xl bg-background border border-border space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold text-foreground">
                  <Swords size={13} className="text-warning shrink-0" />
                  <span className="truncate">
                    {activeObjection.detected_competitor
                      ? `Using ${activeObjection.detected_competitor}`
                      : activeObjection.objection_type.replace(/_/g, ' ')}
                  </span>
                </div>

                {activeObjection.summary && (
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {activeObjection.summary}
                  </p>
                )}

                {/* Competitor Intel Talking Points */}
                {activeObjection.competitor_intel?.kill_points && (
                  <div className="space-y-1.5 pt-2 border-t border-border">
                    <span className="text-xs font-semibold text-foreground">Key Talking Points:</span>
                    <ul className="space-y-1">
                      {activeObjection.competitor_intel.kill_points.map((kp, idx) => (
                        <li key={idx} className="flex items-start gap-1.5 text-xs text-muted-foreground leading-snug">
                          <span className="text-primary font-bold shrink-0">·</span>
                          <span>{kp}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 1-Click Recommended Angle */}
                {activeObjection.competitor_intel?.pivot_angle && onInsertPivotAngle && (
                  <div className="pt-2 border-t border-border space-y-2">
                    <p className="text-xs text-foreground italic">
                      "{activeObjection.competitor_intel.pivot_angle}"
                    </p>
                    <button
                      type="button"
                      onClick={() => onInsertPivotAngle(activeObjection.competitor_intel!.pivot_angle!)}
                      className="w-full py-1.5 rounded-lg text-xs font-semibold bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
                    >
                      <Zap size={12} />
                      <span>Insert This Reply</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-3.5 rounded-xl bg-background border border-border text-xs text-muted-foreground leading-relaxed">
              No active objection detected in this conversation. Use the AI buttons below the chat to draft a follow-up.
            </div>
          )}

          {/* 2. Lead Status (Simple 2x2 Grid) */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-muted-foreground block">Lead Status</span>
            <div className="grid grid-cols-2 gap-1.5">
              {(Object.keys(OUTCOMES) as OutcomeType[]).map((key) => {
                const cfg = OUTCOMES[key];
                const isActive = activeThreadOutcome === key;
                const Icon = cfg.icon;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onToggleOutcome(key)}
                    className={`px-2.5 py-2 rounded-lg text-xs font-medium border flex items-center justify-between cursor-pointer transition-colors ${
                      isActive
                        ? cfg.pillActiveClass
                        : 'bg-background hover:bg-muted text-muted-foreground hover:text-foreground border-border'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 truncate">
                      <Icon size={12} className="shrink-0" />
                      <span className="truncate">{cfg.label}</span>
                    </div>
                    {isActive && <Check size={11} className="shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 3. Pipeline Stage (Clean 1-Line Dropdown Instead of 7 Stacked Rows) */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-muted-foreground block">Pipeline Stage</span>
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsStageMenuOpen(!isStageMenuOpen)}
                className="w-full px-3 py-2 rounded-lg bg-background hover:bg-muted/60 border border-border text-xs font-medium text-foreground flex items-center justify-between cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-2 truncate">
                  <span className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-bold shrink-0">
                    {currentStageIdx + 1}
                  </span>
                  <span className="font-semibold truncate">{currentStageCfg.label}</span>
                </div>
                <ChevronDown
                  size={14}
                  className={`text-muted-foreground transition-transform duration-150 shrink-0 ${
                    isStageMenuOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {isStageMenuOpen && (
                <>
                  <div
                    className="fixed inset-0 z-30"
                    onClick={() => setIsStageMenuOpen(false)}
                  />
                  <div className="absolute left-0 right-0 top-full mt-1.5 z-40 rounded-xl bg-popover text-popover-foreground border border-border shadow-xl p-1 space-y-0.5">
                    {stageKeys.map((stageKey, idx) => {
                      const cfg = DEAL_STAGES[stageKey];
                      const isCurrent = currentDealStage === stageKey;
                      return (
                        <button
                          key={stageKey}
                          type="button"
                          onClick={() => {
                            onUpdateDealStage(stageKey);
                            setIsStageMenuOpen(false);
                          }}
                          className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs flex items-center justify-between transition-colors cursor-pointer ${
                            isCurrent
                              ? 'bg-primary/10 text-primary font-semibold'
                              : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                          }`}
                        >
                          <div className="flex items-center gap-2 truncate">
                            <span className="w-4 h-4 rounded-full bg-muted flex items-center justify-center text-xs font-bold shrink-0">
                              {idx + 1}
                            </span>
                            <span className="truncate">{cfg.label}</span>
                          </div>
                          {isCurrent && <Check size={12} className="shrink-0 text-primary" />}
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* 4. Compact Lead Details (No Duplicate Avatar or Name) */}
          <div className="pt-3 border-t border-border space-y-2 text-xs">
            {selectedThread?.company && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span>Company</span>
                <span className="font-medium text-foreground truncate max-w-40">{selectedThread.company}</span>
              </div>
            )}
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="flex items-center gap-1">
                <Globe size={11} className="text-primary" />
                Timezone
              </span>
              <span className="font-medium text-foreground">
                {selectedThread?.lead_timezone || 'EDT (US East)'}
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
