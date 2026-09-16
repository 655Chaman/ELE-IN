import { create } from "zustand"
import { persist } from "zustand/middleware"
import { HR_TEMPLATES } from "@/lib/eiTemplates"
import type { EITemplate } from "@/lib/eiTemplates"

interface TemplatesState {
  customTemplates: EITemplate[]
  addTemplate: (template: EITemplate) => void
  removeTemplate: (id: string) => void
}

export const useTemplatesStore = create<TemplatesState>()(
  persist(
    (set) => ({
      customTemplates: [],
      addTemplate: (t) => set((state) => ({ customTemplates: [t, ...state.customTemplates] })),
      removeTemplate: (id) => set((state) => ({ customTemplates: state.customTemplates.filter(t => t.id !== id) })),
    }),
    {
      name: "elein-templates-storage",
    }
  )
)
