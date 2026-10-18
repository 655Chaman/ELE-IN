/**
 * @deprecated UI-01 (Zustand Store Collision & Phantom State Remediation):
 * eiCampaignBuilderStore has been unified into useHRTreeStore.
 * All state mutations and reads now proxy directly into useHRTreeStore
 * to prevent split-brain state and ghost drafts.
 */
import { useHRTreeStore } from "./eiTreeStore"

export interface EICampaignBuilderState {
  step: number
  campaignName: string
  leadListId: string | null
  excludeListId: string | null
  excludeOtherCampaigns: boolean
  excludeOtherSenders: boolean
  excludeSameSender: boolean
  stopOnReply: boolean
  senders: string[]
  activeDays: string[]
  startHour: string
  endHour: string
  timezone: string

  setStep: (step: number) => void
  updateForm: (updates: Partial<EICampaignBuilderState>) => void
  resetBuilder: () => void
}

// Layer 1 Environmental Paranoia: Purge legacy phantom storage key from localStorage
if (typeof window !== "undefined") {
  try {
    window.localStorage.removeItem("elein-campaign-builder-storage")
  } catch (_) {}
}

export function useHRCampaignBuilderStore(): EICampaignBuilderState
export function useHRCampaignBuilderStore<T>(selector: (state: EICampaignBuilderState) => T): T
export function useHRCampaignBuilderStore<T>(selector?: (state: EICampaignBuilderState) => T): T | EICampaignBuilderState {
  const treeState = useHRTreeStore()
  const formState = treeState.formState || {}
  const builderState: EICampaignBuilderState = {
    step: treeState.campaignStep ?? 0,
    campaignName: formState.campaignName || "New Campaign",
    leadListId: formState.leadListId || null,
    excludeListId: formState.excludeListId || null,
    excludeOtherCampaigns: formState.excludeOtherCampaigns ?? true,
    excludeOtherSenders: formState.excludeOtherSenders ?? false,
    excludeSameSender: formState.excludeSameSender ?? false,
    stopOnReply: formState.stopOnReply ?? true,
    senders: formState.senders || [],
    activeDays: formState.activeDays || ["Mon", "Tue", "Wed", "Thu", "Fri"],
    startHour: formState.startHour || "09:00",
    endHour: formState.endHour || "17:00",
    timezone: formState.timezone || "America/Los_Angeles",

    setStep: (step: number) => useHRTreeStore.getState().setCampaignStep(step),
    updateForm: (updates: Partial<EICampaignBuilderState>) => {
      const current = useHRTreeStore.getState().formState || {}
      useHRTreeStore.getState().setFormState({ ...current, ...updates })
    },
    resetBuilder: () => {
      useHRTreeStore.getState().reset()
    }
  }

  return selector ? selector(builderState) : builderState
}

// Attach Zustand store-compatible methods (.getState, .setState, .subscribe)
useHRCampaignBuilderStore.getState = (): EICampaignBuilderState => {
  const treeState = useHRTreeStore.getState()
  const formState = treeState.formState || {}
  return {
    step: treeState.campaignStep ?? 0,
    campaignName: formState.campaignName || "New Campaign",
    leadListId: formState.leadListId || null,
    excludeListId: formState.excludeListId || null,
    excludeOtherCampaigns: formState.excludeOtherCampaigns ?? true,
    excludeOtherSenders: formState.excludeOtherSenders ?? false,
    excludeSameSender: formState.excludeSameSender ?? false,
    stopOnReply: formState.stopOnReply ?? true,
    senders: formState.senders || [],
    activeDays: formState.activeDays || ["Mon", "Tue", "Wed", "Thu", "Fri"],
    startHour: formState.startHour || "09:00",
    endHour: formState.endHour || "17:00",
    timezone: formState.timezone || "America/Los_Angeles",

    setStep: (step: number) => useHRTreeStore.getState().setCampaignStep(step),
    updateForm: (updates: Partial<EICampaignBuilderState>) => {
      const current = useHRTreeStore.getState().formState || {}
      useHRTreeStore.getState().setFormState({ ...current, ...updates })
    },
    resetBuilder: () => {
      useHRTreeStore.getState().reset()
    }
  }
}

useHRCampaignBuilderStore.setState = (patch: Partial<EICampaignBuilderState> | ((prev: EICampaignBuilderState) => Partial<EICampaignBuilderState>)) => {
  const current = useHRCampaignBuilderStore.getState()
  const updates = typeof patch === "function" ? patch(current) : patch
  if ("step" in updates && typeof updates.step === "number") {
    useHRTreeStore.getState().setCampaignStep(updates.step)
  }
  const currentForm = useHRTreeStore.getState().formState || {}
  useHRTreeStore.getState().setFormState({ ...currentForm, ...updates })
}

useHRCampaignBuilderStore.subscribe = (listener: (state: EICampaignBuilderState) => void) => {
  return useHRTreeStore.subscribe(() => {
    listener(useHRCampaignBuilderStore.getState())
  })
}

