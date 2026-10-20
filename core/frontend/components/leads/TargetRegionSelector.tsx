import React from 'react';
import { TARGET_REGIONS } from '../../../shared/constants/regions';
import { CustomSelect } from '@/components/ui/select';

interface TargetRegionSelectorProps {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

export const TargetRegionSelector: React.FC<TargetRegionSelectorProps> = ({ value, onChange, error }) => {
  return (
    <div className="flex flex-col gap-1.5 mb-4">
      <label className="text-sm font-medium text-foreground">
        Target Region <span className="text-destructive">*</span>
      </label>
      <p className="text-xs text-muted-foreground mb-1">
        Select the timezone where these leads are located. This replaces location-guessing and ensures accurate outreach scheduling.
      </p>
      <CustomSelect
        value={value}
        onValueChange={onChange}
        placeholder="Select a region..."
        triggerClassName={`h-9 ${error ? 'border-destructive focus-visible:ring-destructive' : 'border-input'}`}
        options={[
          {
            value: "auto",
            label: "Auto-detect / Global (Multi-region by Lead Location)",
          },
          ...TARGET_REGIONS.map((region) => ({
            value: region.timezone,
            label: `${region.label} | ${region.timezone}`,
          })),
        ]}
      />
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
};
