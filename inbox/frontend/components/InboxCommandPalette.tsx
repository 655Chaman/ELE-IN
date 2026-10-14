import { useState, useEffect, useRef } from 'react';
import {
  Calendar, CheckCircle2, Compass, CornerDownLeft, Gamepad2,
  RefreshCw, Search, ShieldCheck, Swords, UserCheck, X, Zap
} from 'lucide-react';
import { ElesiumLogo } from './ElesiumLogo';

interface InboxCommand {
  id: string;
  title: string;
  subtitle: string;
  category: 'Tactics' | 'Pipeline' | 'General';
  icon: any;
  shortcut?: string;
  action: () => void;
}

interface InboxCommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onDeployBattlecard: (tone: 'challenger' | 'consultative' | 'casual') => void;
  onAdvanceDealStage: (stage: any) => void;
  onInsertSlots: () => void;
  onTriggerGhostwriter: () => void;
  onSync: () => void;
  onToggleSimulator: () => void;
  onToggleInspector: () => void;
}

export function InboxCommandPalette({
  isOpen,
  onClose,
  onDeployBattlecard,
  onAdvanceDealStage,
  onInsertSlots,
  onTriggerGhostwriter,
  onSync,
  onToggleSimulator,
  onToggleInspector,
}: InboxCommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands: InboxCommand[] = [
    {
      id: 'ghostwriter',
      title: 'Elesium AI Ghostwriter',
      subtitle: 'Stream intelligent contextual reply based on conversation history',
      category: 'Tactics',
      icon: ElesiumLogo,
      shortcut: 'AI',
      action: () => { onTriggerGhostwriter(); onClose(); },
    },
    {
      id: 'challenger',
      title: 'Deploy Challenger Counter-Pitch',
      subtitle: 'Reframe value, cost of inaction & deliverability jitter',
      category: 'Tactics',
      icon: Zap,
      action: () => { onDeployBattlecard('challenger'); onClose(); },
    },
    {
      id: 'consultative',
      title: 'Deploy Consultative Counter-Pitch',
      subtitle: 'Offer free 25-lead benchmark pilot & collaborative audit',
      category: 'Tactics',
      icon: UserCheck,
      action: () => { onDeployBattlecard('consultative'); onClose(); },
    },
    {
      id: 'casual',
      title: 'Deploy Casual Peer Check-In',
      subtitle: 'Low-pressure check-in honoring their timeline',
      category: 'Tactics',
      icon: Swords,
      action: () => { onDeployBattlecard('casual'); onClose(); },
    },
    {
      id: 'slots',
      title: 'Propose Meeting Slots',
      subtitle: 'Suggest localized slots in prospect timezone',
      category: 'Tactics',
      icon: Calendar,
      action: () => { onInsertSlots(); onClose(); },
    },
    {
      id: 'stage_meeting_confirmed',
      title: 'Advance Stage: Meeting Confirmed',
      subtitle: 'Mark conversation as call successfully booked',
      category: 'Pipeline',
      icon: CheckCircle2,
      action: () => { onAdvanceDealStage('MEETING_CONFIRMED'); onClose(); },
    },
    {
      id: 'stage_closed_won',
      title: 'Advance Stage: Closed Won',
      subtitle: 'Convert opportunity into revenue',
      category: 'Pipeline',
      icon: Compass,
      action: () => { onAdvanceDealStage('CLOSED_WON'); onClose(); },
    },
    {
      id: 'toggle_inspector',
      title: 'Toggle Intelligence Inspector',
      subtitle: 'Show/hide right-rail CRM details & competitive intel',
      category: 'General',
      icon: ShieldCheck,
      shortcut: '⌘I',
      action: () => { onToggleInspector(); onClose(); },
    },
    {
      id: 'sync',
      title: 'Sync LinkedIn Inbox',
      subtitle: 'Run Playwright multi-stage residential scraper',
      category: 'General',
      icon: RefreshCw,
      action: () => { onSync(); onClose(); },
    },
    {
      id: 'simulator',
      title: 'Toggle Objection Simulator Sandbox',
      subtitle: 'Practice handling objections without contacting real prospects',
      category: 'General',
      icon: Gamepad2,
      action: () => { onToggleSimulator(); onClose(); },
    },
  ];

  const filtered = commands.filter(
    (c) =>
      c.title.toLowerCase().includes(query.toLowerCase()) ||
      c.subtitle.toLowerCase().includes(query.toLowerCase()) ||
      c.category.toLowerCase().includes(query.toLowerCase())
  );

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  if (!isOpen) return null;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % (filtered.length || 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filtered.length) % (filtered.length || 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[selectedIndex]) {
        filtered[selectedIndex].action();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 p-4 bg-background/80 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className="fixed inset-0 -z-10"
        onClick={onClose}
      />
      <div className="w-full max-w-xl rounded-xl bg-popover text-popover-foreground border border-border shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
        <div className="flex items-center px-4 border-b border-border bg-card">
          <Search size={16} className="text-muted-foreground shrink-0 mr-3" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command, tactic, or pipeline stage... (ESC to close)"
            className="w-full py-3.5 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="p-1 text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <div className="max-h-80 overflow-y-auto p-2 space-y-1">
          {filtered.length === 0 ? (
            <div className="p-8 text-center text-xs text-muted-foreground">
              No matching inbox commands found.
            </div>
          ) : (
            filtered.map((cmd, idx) => {
              const Icon = cmd.icon;
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={cmd.id}
                  onClick={cmd.action}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`p-2.5 rounded-lg flex items-center justify-between cursor-pointer transition-colors ${
                    isSelected
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted text-foreground'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                        isSelected
                          ? 'bg-primary-foreground/20 text-primary-foreground'
                          : 'bg-muted text-primary'
                      }`}
                    >
                      <Icon size={14} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold truncate flex items-center gap-2">
                        <span>{cmd.title}</span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-normal uppercase ${
                            isSelected
                              ? 'bg-primary-foreground/20 text-primary-foreground'
                              : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {cmd.category}
                        </span>
                      </div>
                      <div
                        className={`text-xs truncate mt-0.5 ${
                          isSelected ? 'text-primary-foreground/85' : 'text-muted-foreground'
                        }`}
                      >
                        {cmd.subtitle}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    {cmd.shortcut && (
                      <kbd
                        className={`text-xs px-1.5 py-0.5 rounded-md border font-mono ${
                          isSelected
                            ? 'border-primary-foreground/30 bg-primary-foreground/10 text-primary-foreground'
                            : 'border-border bg-muted text-muted-foreground'
                        }`}
                      >
                        {cmd.shortcut}
                      </kbd>
                    )}
                    {isSelected && (
                      <CornerDownLeft size={13} className="text-primary-foreground opacity-80" />
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="px-4 py-2 border-t border-border bg-muted/50 flex items-center justify-between text-xs text-muted-foreground">
          <span>Navigate with <kbd className="font-mono bg-background px-1 rounded-md border border-border">↑</kbd> <kbd className="font-mono bg-background px-1 rounded-md border border-border">↓</kbd></span>
          <span>Press <kbd className="font-mono bg-background px-1 rounded-md border border-border">↵</kbd> to execute</span>
        </div>
      </div>
    </div>
  );
}
