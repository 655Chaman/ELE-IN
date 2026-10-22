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
  senderIds?: string[]
  activeDays: string[]
  startHour: string
  endHour: string
  schedule?: {
    startTime: string
    endTime: string
    start_hour?: number
    end_hour?: number
    weekend_sending?: boolean
  }
  timezone: string

  setStep: (step: number) => void
  updateForm: (updates: Partial<EICampaignBuilderState>) => void
  resetBuilder: () => void
}

function mapBuilderUpdatesToTreeForm(updates: Partial<EICampaignBuilderState>, currentForm: any): any {
  const mapped: any = { ...updates }
  if (updates.senders !== undefined) {
    mapped.senderIds = updates.senders
  }
  if (updates.senderIds !== undefined) {
    mapped.senders = updates.senderIds
  }
  if (updates.startHour !== undefined || updates.endHour !== undefined || updates.schedule !== undefined) {
    const prevSchedule = currentForm.schedule || {}
    const startTime = updates.startHour || updates.schedule?.startTime || prevSchedule.startTime || "09:00"
    const endTime = updates.endHour || updates.schedule?.endTime || prevSchedule.endTime || "17:00"
    mapped.schedule = {
      ...prevSchedule,
      ...(updates.schedule || {}),
      startTime,
      endTime,
      start_hour: parseInt(startTime.split(":")[0], 10) || 9,
      end_hour: parseInt(endTime.split(":")[0], 10) || 17,
    }
  }
  return mapped
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
    senders: formState.senderIds || formState.senders || [],
    senderIds: formState.senderIds || formState.senders || [],
    activeDays: formState.activeDays || ["Mon", "Tue", "Wed", "Thu", "Fri"],
    startHour: formState.schedule?.startTime || formState.startHour || "09:00",
    endHour: formState.schedule?.endTime || formState.endHour || "17:00",
    schedule: formState.schedule || {
      startTime: formState.startHour || "09:00",
      endTime: formState.endHour || "17:00",
      start_hour: 9,
      end_hour: 17
    },
    timezone: formState.timezone || "America/Los_Angeles",

    setStep: (step: number) => useHRTreeStore.getState().setCampaignStep(step),
    updateForm: (updates: Partial<EICampaignBuilderState>) => {
      if ("step" in updates && typeof (updates as any).step === "number") {
        useHRTreeStore.getState().setCampaignStep((updates as any).step)
      }
      const current = useHRTreeStore.getState().formState || {}
      const mapped = mapBuilderUpdatesToTreeForm(updates, current)
      useHRTreeStore.getState().setFormState({ ...current, ...mapped })
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
    senders: formState.senderIds || formState.senders || [],
    senderIds: formState.senderIds || formState.senders || [],
    activeDays: formState.activeDays || ["Mon", "Tue", "Wed", "Thu", "Fri"],
    startHour: formState.schedule?.startTime || formState.startHour || "09:00",
    endHour: formState.schedule?.endTime || formState.endHour || "17:00",
    schedule: formState.schedule || {
      startTime: formState.startHour || "09:00",
      endTime: formState.endHour || "17:00",
      start_hour: 9,
      end_hour: 17
    },
    timezone: formState.timezone || "America/Los_Angeles",

    setStep: (step: number) => useHRTreeStore.getState().setCampaignStep(step),
    updateForm: (updates: Partial<EICampaignBuilderState>) => {
      if ("step" in updates && typeof (updates as any).step === "number") {
        useHRTreeStore.getState().setCampaignStep((updates as any).step)
      }
      const current = useHRTreeStore.getState().formState || {}
      const mapped = mapBuilderUpdatesToTreeForm(updates, current)
      useHRTreeStore.getState().setFormState({ ...current, ...mapped })
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
  const mapped = mapBuilderUpdatesToTreeForm(updates, currentForm)
  useHRTreeStore.getState().setFormState({ ...currentForm, ...mapped })
}

useHRCampaignBuilderStore.subscribe = (listener: (state: EICampaignBuilderState) => void) => {
  return useHRTreeStore.subscribe(() => {
    listener(useHRCampaignBuilderStore.getState())
  })
}

