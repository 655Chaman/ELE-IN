/**
 * @deprecated This store is not connected to the live data layer.
 * EleInCampaigns.tsx fetches campaign data directly via SWR.
 * Do not add new logic here. This file is a candidate for deletion
 * once all references are confirmed removed.
 */
import { create } from "zustand"
import { persist } from "zustand/middleware"

export interface Campaign {
  id: string
  name: string
  description: string
  status: "ACTIVE" | "PAUSED" | "DRAFT"
  senders: string[]
  leadCount: number
  sent: number
  accepted: number
  replies: number
  createdAt: string
}

interface CampaignsState {
  campaigns: Campaign[]
  addCampaign: (campaign: Campaign) => void
  removeCampaign: (id: string) => void
  toggleStatus: (id: string) => void
}

const INITIAL_CAMPAIGNS: Campaign[] = []

export const useHRCampaignsStore = create<CampaignsState>()(
  persist(
    (set) => ({
      campaigns: INITIAL_CAMPAIGNS,
      addCampaign: (campaign) => set((state) => ({ campaigns: [campaign, ...state.campaigns] })),
      removeCampaign: (id) => set((state) => ({ campaigns: state.campaigns.filter(c => c.id !== id) })),
      toggleStatus: (id) => set((state) => {
        const campaign = state.campaigns.find(c => c.id === id)
        if (campaign?.status === "DRAFT") {
          throw new Error('Cannot toggle a DRAFT campaign. Publish it first.')
        }
        return {
          campaigns: state.campaigns.map(c => {
            if (c.id !== id) return c
            return { ...c, status: c.status === "ACTIVE" ? "PAUSED" : "ACTIVE" }
          })
        }
      })
    }),
    {
      name: "elein-campaigns-storage"
    }
  )
)
