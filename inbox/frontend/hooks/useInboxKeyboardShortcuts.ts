import { useEffect } from 'react';

interface ShortcutHandlers {
  onNextThread?: () => void;
  onPrevThread?: () => void;
  onArchiveThread?: () => void;
  onFocusComposer?: () => void;
  onToggleInspector?: () => void;
  onOpenCommandPalette?: () => void;
  onEscape?: () => void;
  onSnoozeThread?: () => void;
}

export function useInboxKeyboardShortcuts({
  onNextThread,
  onPrevThread,
  onArchiveThread,
  onFocusComposer,
  onToggleInspector,
  onOpenCommandPalette,
  onEscape,
  onSnoozeThread,
}: ShortcutHandlers) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K opens Command Palette anywhere
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onOpenCommandPalette?.();
        return;
      }

      // Cmd+I or Ctrl+I toggles intelligence inspector
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'i') {
        e.preventDefault();
        onToggleInspector?.();
        return;
      }

      // Escape handles modals / popovers
      if (e.key === 'Escape') {
        onEscape?.();
        return;
      }

      // If user is currently typing in an input, textarea, contenteditable, or ARIA textbox, don't trigger single-key nav
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable ||
          target.getAttribute('role') === 'textbox')
      ) {
        return;
      }

      // Paranoia Layer 1 (FLAW-A11Y-03): Strictly guard bare single keys against modifiers (Cmd+R reload, AltGr special chars)
      const isBareKey = !e.metaKey && !e.ctrlKey && !e.altKey;

      // Superhuman-style single key triage:
      if (isBareKey && (e.key === 'j' || e.key === 'ArrowDown')) {
        e.preventDefault();
        onNextThread?.();
      } else if (isBareKey && (e.key === 'k' || e.key === 'ArrowUp')) {
        e.preventDefault();
        onPrevThread?.();
      } else if (isBareKey && e.key === 'e') {
        e.preventDefault();
        onArchiveThread?.();
      } else if (isBareKey && e.key === 'r') {
        e.preventDefault();
        onFocusComposer?.();
      } else if (isBareKey && e.key === 'h') {
        e.preventDefault();
        onSnoozeThread?.();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    onNextThread,
    onPrevThread,
    onArchiveThread,
    onFocusComposer,
    onToggleInspector,
    onOpenCommandPalette,
    onEscape,
    onSnoozeThread,
  ]);
}
