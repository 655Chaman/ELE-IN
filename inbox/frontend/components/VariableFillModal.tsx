import { useState, useEffect } from 'react';
import { AlertTriangle, Check, X } from 'lucide-react';

interface VariableFillModalProps {
  isOpen: boolean;
  onClose: () => void;
  text: string;
  onApplyAndSend: (resolvedText: string) => void;
  defaultValues?: Record<string, string>;
}

export function VariableFillModal({
  isOpen,
  onClose,
  text,
  onApplyAndSend,
  defaultValues = {},
}: VariableFillModalProps) {
  const [variables, setVariables] = useState<string[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!isOpen) return;
    const matches = Array.from(text.matchAll(/\{\{([a-zA-Z0-9_]+)\}\}/g));
    const unique = Array.from(new Set(matches.map((m) => m[1])));
    setVariables(unique);

    const initial: Record<string, string> = {};
    unique.forEach((v) => {
      initial[v] = defaultValues[v] || '';
    });
    setValues(initial);
  }, [isOpen, text, defaultValues]);

  if (!isOpen) return null;

  const handleApply = () => {
    let resolved = text;
    variables.forEach((v) => {
      const val = values[v] || `{{${v}}}`;
      resolved = resolved.replaceAll(`{{${v}}}`, val);
    });
    onApplyAndSend(resolved);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="w-full max-w-md rounded-xl bg-card border border-border p-5 shadow-2xl space-y-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-warning/10 border border-warning/20 flex items-center justify-center text-warning">
              <AlertTriangle size={18} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">
                Unresolved Template Variables
              </h3>
              <p className="text-xs text-muted-foreground">
                Fill in bracketed variables before sending to the prospect.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground p-1 rounded-lg transition-colors cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-2.5 py-1 max-h-60 overflow-y-auto">
          {variables.map((variable) => (
            <div key={variable} className="space-y-1">
              <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                <code className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded-md text-primary">
                  {`{{${variable}}}`}
                </code>
                <span className="text-xs text-muted-foreground">Field</span>
              </label>
              <input
                type="text"
                value={values[variable] || ''}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [variable]: e.target.value }))
                }
                placeholder={`Value for ${variable}...`}
                className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary/60 transition-colors"
                autoFocus={variable === variables[0]}
              />
            </div>
          ))}
        </div>

        <div className="pt-2 border-t border-border flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            Review Draft
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onApplyAndSend(text)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground border border-border transition-colors cursor-pointer"
            >
              Send Unresolved
            </button>
            <button
              type="button"
              onClick={handleApply}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground shadow-xs flex items-center gap-1.5 cursor-pointer transition-all"
            >
              <Check size={13} />
              <span>Fill &amp; Send</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
