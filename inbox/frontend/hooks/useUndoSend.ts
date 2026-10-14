import { useRef, useCallback } from 'react';
import { toast } from 'sonner';

interface PendingDispatch {
  id: string;
  senderName: string;
  leadId: string | null;
  messageText: string;
  timeoutId: NodeJS.Timeout;
}

export function useUndoSend() {
  const pendingQueueRef = useRef<Map<string, PendingDispatch>>(new Map());

  const queueSend = useCallback(
    (
      payload: {
        senderName: string;
        leadId: string | null;
        messageText: string;
      },
      onActualDispatch: () => Promise<void>,
      onUndo: (restoredText: string) => void,
      delayMs: number = 4000
    ) => {
      const dispatchId = `send-${Date.now()}`;

      const timeoutId = setTimeout(async () => {
        pendingQueueRef.current.delete(dispatchId);
        try {
          await onActualDispatch();
        } catch {
          // Handled in onActualDispatch
        }
      }, delayMs);

      pendingQueueRef.current.set(dispatchId, {
        id: dispatchId,
        senderName: payload.senderName,
        leadId: payload.leadId,
        messageText: payload.messageText,
        timeoutId,
      });

      toast.info(`Sending reply in ${Math.round(delayMs / 1000)}s... /* ds-allow-hardcode */`, {
        id: dispatchId,
        duration: delayMs,
        action: {
          label: 'Undo (Cmd+Z)',
          onClick: () => {
            const item = pendingQueueRef.current.get(dispatchId);
            if (item) {
              clearTimeout(item.timeoutId);
              pendingQueueRef.current.delete(dispatchId);
              onUndo(item.messageText);
              toast.dismiss(dispatchId);
              toast.success('Send undone. Draft restored.');
            }
          },
        },
      });
    },
    []
  );

  return { queueSend };
}
