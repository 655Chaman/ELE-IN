import { useState } from 'react';
import { Calendar, Check, Clock, Globe, X } from 'lucide-react';

export interface SlotCandidate {
  id: string;
  label: string;
  timeProspect: string;
  timeUser?: string;
  selected: boolean;
}

interface TimezoneSlotPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  leadName: string;
  leadTimezone?: string;
  onInsertSlots: (formattedText: string) => void;
}

export function TimezoneSlotPickerModal({
  isOpen,
  onClose,
  leadName,
  leadTimezone = 'EDT',
  onInsertSlots,
}: TimezoneSlotPickerModalProps) {
  const [slots, setSlots] = useState<SlotCandidate[]>([
    {
      id: '1',
      label: 'Thursday 10:00 AM',
      timeProspect: 'Thursday at 10:00 AM ' + leadTimezone,
      selected: true,
    },
    {
      id: '2',
      label: 'Friday 2:00 PM',
      timeProspect: 'Friday at 2:00 PM ' + leadTimezone,
      selected: true,
    },
    {
      id: '3',
      label: 'Monday 11:30 AM',
      timeProspect: 'Monday at 11:30 AM ' + leadTimezone,
      selected: true,
    },
  ]);

  if (!isOpen) return null;

  const toggleSlot = (id: string) => {
    setSlots((prev) =>
      prev.map((s) => (s.id === id ? { ...s, selected: !s.selected } : s))
    );
  };

  const handleConfirm = () => {
    const selected = slots.filter((s) => s.selected);
    if (selected.length === 0) {
      onClose();
      return;
    }
    const lines = selected.map((s) => `• ${s.timeProspect}`);
    const text = `Here are a few times that work well on my calendar:\n${lines.join(
      '\n'
    )}\n\nDo any of these work on your end, ${leadName || 'there'}?`;
    onInsertSlots(text);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="w-full max-w-md rounded-xl bg-card border border-border p-5 shadow-2xl space-y-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <Calendar size={18} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">
                Propose Meeting Slots
              </h3>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
                <Globe size={11} className="text-primary" />
                <span>Prospect Timezone: <strong className="text-foreground">{leadTimezone}</strong></span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground p-1 rounded-lg transition-colors cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-2 py-1">
          <p className="text-xs text-muted-foreground">
            Select optimal calendar windows aligned to {leadName}'s business hours:
          </p>

          <div className="space-y-1.5">
            {slots.map((slot) => (
              <div
                key={slot.id}
                onClick={() => toggleSlot(slot.id)}
                className={`p-3 rounded-lg border flex items-center justify-between cursor-pointer transition-all ${
                  slot.selected
                    ? 'bg-primary/10 border-primary/40 text-foreground'
                    : 'bg-muted/30 border-border text-muted-foreground hover:bg-muted/60'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div
                    className={`w-4 h-4 rounded-md flex items-center justify-center border transition-all ${
                      slot.selected
                        ? 'bg-primary border-primary text-primary-foreground'
                        : 'border-muted-foreground/40 bg-background'
                    }`}
                  >
                    {slot.selected && <Check size={11} strokeWidth={3} />}
                  </div>
                  <span className="text-xs font-semibold">{slot.timeProspect}</span>
                </div>
                <Clock size={13} className="text-muted-foreground" />
              </div>
            ))}
          </div>
        </div>

        <div className="pt-2 border-t border-border flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground shadow-xs flex items-center gap-1.5 cursor-pointer transition-all"
          >
            <Check size={13} />
            <span>Insert Selected Slots</span>
          </button>
        </div>
      </div>
    </div>
  );
}
