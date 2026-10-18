import { useState, type KeyboardEvent, type RefObject } from 'react';
import {
  AlertTriangle, Calendar, ChevronDown, FileText, Loader2,
  Send, Square, Undo2
} from 'lucide-react';
import { ElesiumLogo } from '@/components/ElesiumLogo';
import {
  QUICK_STARTERS, type ObjectionData
} from '../types';

interface ComposerStationProps {
  replyText: string;
  onReplyTextChange: (text: string) => void;
  onSend: () => void;
  isSending: boolean;
  isDraftingAI: boolean;
  activeAIIntent?: string | null;
  onTriggerGhostwriter: (intent?: string) => void;
  onStopDrafting: () => void;
  savedDraftBeforeAI: string | null;
  onRestoreDraft: () => void;
  hasTemplateVars: boolean;
  activeObjection?: ObjectionData | null;
  activeBattlecardTone?: 'challenger' | 'consultative' | 'casual' | null;
  isGeneratingBattlecard?: boolean;
  onApplyBattlecardTone?: (tone: 'challenger' | 'consultative' | 'casual') => void;
  onOpenSlotPicker: () => void;
  isInsertingSlots: boolean;
  sendOnEnter: boolean;
  onSendOnEnterChange: (val: boolean) => void;
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
}

export function ComposerStation({
  replyText,
  onReplyTextChange,
  onSend,
  isSending,
  isDraftingAI,
  activeAIIntent: _activeAIIntent,
  onTriggerGhostwriter,
  onStopDrafting,
  savedDraftBeforeAI,
  onRestoreDraft,
  hasTemplateVars,
  activeObjection: _activeObjection,
  activeBattlecardTone: _activeBattlecardTone,
  isGeneratingBattlecard: _isGeneratingBattlecard,
  onApplyBattlecardTone: _onApplyBattlecardTone,
  onOpenSlotPicker,
  isInsertingSlots,
  sendOnEnter,
  onSendOnEnterChange: _onSendOnEnterChange,
  textareaRef,
}: ComposerStationProps) {
  const [isTemplatesMenuOpen, setIsTemplatesMenuOpen] = useState(false);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (sendOnEnter && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    } else if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="border-t border-border bg-card shrink-0">
      {/* Composer Textarea Container */}
      <div className="p-3">
        {/* Restorable Draft Banner */}
        {savedDraftBeforeAI && savedDraftBeforeAI !== replyText && (
          <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground bg-muted/60 px-3 py-1.5 rounded-lg border border-border">
            <span className="flex items-center gap-1.5 text-foreground">
              <ElesiumLogo size={13} />
              AI draft applied.
            </span>
            <button
              type="button"
              onClick={onRestoreDraft}
              className="text-primary hover:underline font-semibold flex items-center gap-1 cursor-pointer"
            >
              <Undo2 size={12} />
              Undo
            </button>
          </div>
        )}

        {/* Template Variable Warning Pill */}
        {hasTemplateVars && (
          <div className="mb-2 flex items-center gap-1.5 text-xs text-warning bg-warning/10 px-3 py-1.5 rounded-lg border border-warning/20">
            <AlertTriangle size={13} className="shrink-0 text-warning" />
            <span>Contains <code className="bg-muted px-1.5 py-0.5 rounded-md text-xs font-mono border border-border">&#123;&#123;variables&#125;&#125;</code> - you will be prompted to fill them before sending.</span>
          </div>
        )}

        {/* Textarea Box */}
        <div className="flex flex-col rounded-xl bg-background border border-border focus-within:border-primary transition-all p-3">
          <textarea
            ref={textareaRef}
            value={replyText}
            onChange={(e) => onReplyTextChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Write a reply, or click AI Write below to draft..."
            maxLength={4000}
            rows={3}
            className="w-full bg-transparent border-none outline-none text-sm px-1 py-0.5 text-foreground placeholder:text-muted-foreground disabled:opacity-50 resize-none min-h-14 max-h-36 leading-relaxed"
            disabled={isSending}
          />

          {/* Bottom Dock: Real-World Tools & Primary Send Action */}
          <div className="mt-2 pt-2 border-t border-border flex items-center justify-between gap-2 text-xs">
            {/* Left Tools */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {/* Templates Dropdown Menu */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setIsTemplatesMenuOpen(!isTemplatesMenuOpen)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-card hover:bg-muted text-foreground border border-border shadow-2xs transition-colors cursor-pointer whitespace-nowrap"
                >
                  <FileText size={12} className="text-muted-foreground" />
                  <span>Templates</span>
                  <ChevronDown
                    size={11}
                    className={`text-muted-foreground transition-transform duration-150 ${
                      isTemplatesMenuOpen ? 'rotate-180' : ''
                    }`}
                  />
                </button>

                {isTemplatesMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-30"
                      onClick={() => setIsTemplatesMenuOpen(false)}
                    />
                    <div className="absolute left-0 bottom-full mb-1.5 z-40 w-52 rounded-xl bg-popover text-popover-foreground border border-border shadow-xl p-1.5 space-y-0.5 text-xs">
                      <div className="text-xs uppercase font-semibold text-muted-foreground px-2 py-1">
                        Quick Templates
                      </div>
                      {QUICK_STARTERS.map((preset) => (
                        <button
                          key={preset.label}
                          type="button"
                          onClick={() => {
                            onReplyTextChange(preset.text);
                            setIsTemplatesMenuOpen(false);
                          }}
                          className="w-full text-left px-2 py-1.5 rounded-md text-xs hover:bg-muted text-foreground transition-colors cursor-pointer flex items-center gap-2"
                        >
                          <FileText size={12} className="text-muted-foreground shrink-0" />
                          <span className="truncate">{preset.label}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              {/* Propose Slots Button */}
              <button
                type="button"
                onClick={onOpenSlotPicker}
                disabled={isInsertingSlots}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-card hover:bg-muted text-foreground border border-border shadow-2xs transition-colors cursor-pointer disabled:opacity-50 whitespace-nowrap"
                title="Insert available meeting times in prospect's timezone"
              >
                {isInsertingSlots ? (
                  <Loader2 size={12} className="animate-spin text-primary" />
                ) : (
                  <Calendar size={12} className="text-muted-foreground" />
                )}
                <span>Propose Times</span>
              </button>

              {/* AI Write / Stop Button */}
              {isDraftingAI ? (
                <button
                  type="button"
                  onClick={onStopDrafting}
                  title="Stop AI generation"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-destructive/10 text-destructive hover:bg-destructive/20 border border-destructive/20 transition-colors rounded-md text-xs font-semibold cursor-pointer whitespace-nowrap"
                >
                  <Square size={11} className="fill-current" />
                  <ElesiumLogo size={12} />
                  <span>Stop AI</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => onTriggerGhostwriter('unknown')}
                  disabled={isSending}
                  title="Auto-write a smart reply with AI"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20 transition-colors rounded-md disabled:opacity-50 text-xs font-semibold cursor-pointer whitespace-nowrap"
                >
                  <ElesiumLogo size={13} />
                  <span>AI Write</span>
                </button>
              )}
            </div>

            {/* Right Primary Send Action */}
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={onSend}
                disabled={
                  !replyText.trim() ||
                  isSending ||
                  isDraftingAI
                }
                title="Send reply (Cmd+Enter)"
                className="px-4 py-1.5 transition-all rounded-md disabled:opacity-50 disabled:bg-muted disabled:text-muted-foreground flex items-center gap-1.5 text-xs font-semibold cursor-pointer bg-primary text-primary-foreground hover:bg-primary/90 whitespace-nowrap shadow-xs"
              >
                {isSending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Send size={12} />
                )}
                <span>{isSending ? 'Sending...' : 'Send'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
