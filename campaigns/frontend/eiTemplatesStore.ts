import { create } from "zustand"
import { persist } from "zustand/middleware"
import { HR_TEMPLATES } from "@/lib/eiTemplates"
import type { EITemplate } from "@/lib/eiTemplates"

export const MAX_SPINTAX_CHARS = 2000
export const MAX_SPINTAX_DEPTH = 3

/**
 * Three-Layer Paranoia Spintax & Template Validation (UI-15)
 * - Layer 0 (Foundational): Enforces character length <= 2,000.
 * - Layer 1 (Environmental): Enforces spintax nesting depth <= 3 and checks for balanced braces to prevent backend ReDoS.
 * - Layer 2 (Human Paranoia): Provides clear error strings and safe template sanitization.
 */
export function validateSpintax(text: string): { valid: boolean; error?: string } {
  if (!text || typeof text !== "string") {
    return { valid: true }
  }

  if (text.length > MAX_SPINTAX_CHARS) {
    return {
      valid: false,
      error: `Template exceeds maximum length of ${MAX_SPINTAX_CHARS} characters (currently ${text.length}).`
    }
  }

  let currentDepth = 0
  let maxDepth = 0

  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === "{") {
      // Check if it's a variable {{var}} or spintax {opt1|opt2}
      if (i + 1 < text.length && text[i + 1] === "{") {
        i++ // Skip next brace for {{var}}
        continue
      }
      currentDepth++
      if (currentDepth > maxDepth) {
        maxDepth = currentDepth
      }
      if (currentDepth > MAX_SPINTAX_DEPTH) {
        return {
          valid: false,
          error: `Spintax nesting exceeds maximum allowed depth of ${MAX_SPINTAX_DEPTH} levels.`
        }
      }
    } else if (ch === "}") {
      if (i + 1 < text.length && text[i + 1] === "}") {
        i++ // Skip next brace for }}
        continue
      }
      currentDepth--
      if (currentDepth < 0) {
        return {
          valid: false,
          error: "Unbalanced spintax: found closing '}' without matching opening '{'."
        }
      }
    }
  }

  if (currentDepth !== 0) {
    return {
      valid: false,
      error: "Unbalanced spintax: found unclosed opening '{'."
    }
  }

  return { valid: true }
}

export function sanitizeSpintax(text: string): string {
  if (!text || typeof text !== "string") return ""
  return text.slice(0, MAX_SPINTAX_CHARS)
}

interface TemplatesState {
  customTemplates: EITemplate[]
  addTemplate: (template: EITemplate) => void
  removeTemplate: (id: string) => void
}

export const useTemplatesStore = create<TemplatesState>()(
  persist(
    (set) => ({
      customTemplates: [],
      addTemplate: (t) => {
        // Paranoia Layer 1 & 2 (UI-15): Guard against oversized or malicious templates
        const sanitizedNodes = (t.nodes || []).map((node) => {
          const data = { ...(node.data || {}) }
          for (const key of ["note", "message", "body", "script", "pitch"]) {
            if (typeof data[key] === "string") {
              const res = validateSpintax(data[key])
              if (!res.valid) {
                data[key] = sanitizeSpintax(data[key])
              }
            }
          }
          return { ...node, data }
        })
        const cleanTemplate: EITemplate = {
          ...t,
          nodes: sanitizedNodes
        }
        set((state) => ({ customTemplates: [cleanTemplate, ...state.customTemplates] }))
      },
      removeTemplate: (id) => set((state) => ({ customTemplates: state.customTemplates.filter(t => t.id !== id) })),
    }),
    {
      name: "elein-templates-storage",
    }
  )
)
