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

  const stack: ("variable" | "spintax")[] = []
  let maxDepth = 0

  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === "{") {
      if (i + 1 < text.length && text[i + 1] === "{") {
        stack.push("variable")
        i++ // Skip second brace for {{var}}
        continue
      }
      stack.push("spintax")
      const currentDepth = stack.filter(s => s === "spintax").length
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
      // Check if top of stack is a variable and next char is also }
      if (stack.length > 0 && stack[stack.length - 1] === "variable" && i + 1 < text.length && text[i + 1] === "}") {
        stack.pop()
        i++ // Skip second brace for }}
        continue
      }
      if (stack.length === 0) {
        return {
          valid: false,
          error: "Unbalanced spintax: found closing '}' without matching opening '{'."
        }
      }
      const top = stack.pop()
      if (top !== "spintax") {
        return {
          valid: false,
          error: "Unbalanced spintax: mismatched braces."
        }
      }
    }
  }

  if (stack.length !== 0) {
    const unclosedType = stack[stack.length - 1]
    return {
      valid: false,
      error: unclosedType === "variable" 
        ? "Unbalanced spintax: found unclosed variable '{{'."
        : "Unbalanced spintax: found unclosed opening '{'."
    }
  }

  return { valid: true }
}

// Paranoia Layer 0 & 1 (FLAW-FE-20): Resiliently balance and repair braces rather than simply slicing
export function sanitizeSpintax(text: string): string {
  if (!text || typeof text !== "string") return ""
  // Reserve characters for trailing closing braces if truncation is needed
  const budget = MAX_SPINTAX_CHARS - 10
  const trimmed = text.length > MAX_SPINTAX_CHARS ? text.slice(0, budget) : text

  let result = ""
  const braceStack: ("double" | "single")[] = []
  let skippedLevels = 0

  for (let i = 0; i < trimmed.length; i++) {
    if (trimmed[i] === "{" && i + 1 < trimmed.length && trimmed[i + 1] === "{") {
      braceStack.push("double")
      result += "{{"
      i++ // Skip second {
    } else if (trimmed[i] === "{") {
      const singleDepth = braceStack.filter(b => b === "single").length
      if (singleDepth >= MAX_SPINTAX_DEPTH) {
        skippedLevels++
        continue
      }
      braceStack.push("single")
      result += "{"
    } else if (trimmed[i] === "}" && i + 1 < trimmed.length && trimmed[i + 1] === "}") {
      const lastDouble = braceStack.lastIndexOf("double")
      if (lastDouble !== -1) {
        while (braceStack.length > lastDouble + 1) {
          const inner = braceStack.pop()
          if (inner === "single") result += "}"
        }
        braceStack.pop()
        result += "}}"
        i++ // Skip second }
      } else {
        // Stray }}, omit
        i++
      }
    } else if (trimmed[i] === "}") {
      if (skippedLevels > 0) {
        skippedLevels--
        continue
      }
      const lastSingle = braceStack.lastIndexOf("single")
      if (lastSingle !== -1) {
        while (braceStack.length > lastSingle + 1) {
          const inner = braceStack.pop()
          if (inner === "single") result += "}"
          else if (inner === "double") result += "}}"
        }
        braceStack.pop()
        result += "}"
      } else {
        // Stray single }, omit
      }
    } else {
      result += trimmed[i]
    }
  }

  // Gracefully close any trailing unclosed braces left by truncation
  while (braceStack.length > 0) {
    const unclosed = braceStack.pop()
    if (unclosed === "single") {
      result += "}"
    } else if (unclosed === "double") {
      result += "}}"
    }
  }

  return result
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
