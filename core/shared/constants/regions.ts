import regionsData from './regions.json';

export interface Region {
  label: string;
  timezone: string;
}

export const TARGET_REGIONS: Region[] = regionsData;
