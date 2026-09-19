import React from 'react';
import { TARGET_REGIONS } from '../../../shared/constants/regions';

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
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`flex h-9 w-full rounded-md border ${error ? 'border-destructive' : 'border-input'} bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50`}
      >
        <option value="" disabled>Select a region...</option>
        {TARGET_REGIONS.map((region) => (
          <option key={region.timezone} value={region.timezone}>
            {region.label} | {region.timezone}
          </option>
        ))}
      </select>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
};
