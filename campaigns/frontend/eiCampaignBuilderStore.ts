import { create } from "zustand"
import { persist } from "zustand/middleware"

export interface EICampaignBuilderState {
  step: number
  campaignName: string
  leadListId: string | null
  excludeListId: string | null
  excludeOtherCampaigns: boolean
  excludeOtherSenders: boolean
  excludeSameSender: boolean
  senders: string[]
  activeDays: string[]
  startHour: string
  endHour: string
  timezone: string

  setStep: (step: number) => void
  updateForm: (updates: Partial<EICampaignBuilderState>) => void
  resetBuilder: () => void
}

const initialState = {
  step: 0,
  campaignName: "New Campaign",
  leadListId: null,
  excludeListId: null,
  excludeOtherCampaigns: true,
  excludeOtherSenders: false,
  excludeSameSender: false,
  senders: [],
  activeDays: ["Mon", "Tue", "Wed", "Thu", "Fri"],
  startHour: "09:00",
  endHour: "17:00",
  timezone: "America/Los_Angeles"
}

export const useHRCampaignBuilderStore = create<EICampaignBuilderState>()(
  persist(
    (set) => ({
      ...initialState,
      setStep: (step) => set({ step }),
      updateForm: (updates) => set((state) => ({ ...state, ...updates })),
      resetBuilder: () => set(initialState)
    }),
    {
      name: "elein-campaign-builder-storage"
    }
  )
)
