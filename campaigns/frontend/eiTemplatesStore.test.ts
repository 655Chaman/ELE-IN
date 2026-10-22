import { describe, it, expect } from "bun:test"
import { validateSpintax, sanitizeSpintax, MAX_SPINTAX_CHARS, MAX_SPINTAX_DEPTH } from "./eiTemplatesStore"

describe("Three-Layer Paranoia Spintax Hardening (FLAW-FE-20)", () => {
  it("Layer 0: Handles valid spintax and variables cleanly", () => {
    const text = "Hello {{first_name}}, {glad|excited} to connect!"
    expect(validateSpintax(text).valid).toBe(true)
    expect(sanitizeSpintax(text)).toBe(text)
  })

  it("Layer 1: Balances unclosed single braces", () => {
    const unclosed = "Hi {first_name|colleague"
    const validated = validateSpintax(unclosed)
    expect(validated.valid).toBe(false)

    const sanitized = sanitizeSpintax(unclosed)
    expect(sanitized).toBe("Hi {first_name|colleague}")
    expect(validateSpintax(sanitized).valid).toBe(true)
  })

  it("Layer 1: Balances unclosed double braces (variables)", () => {
    const unclosed = "Hello {{first_name"
    const sanitized = sanitizeSpintax(unclosed)
    expect(sanitized).toBe("Hello {{first_name}}")
    expect(validateSpintax(sanitized).valid).toBe(true)
  })

  it("Layer 2: Strips stray unmatched closing braces that could break backend parser", () => {
    const stray = "Hey there} {{name}}! How are you doing?}"
    const sanitized = sanitizeSpintax(stray)
    expect(sanitized).toBe("Hey there {{name}}! How are you doing?")
    expect(validateSpintax(sanitized).valid).toBe(true)
  })

  it("Layer 1: Caps excessive nesting depth at MAX_SPINTAX_DEPTH (3)", () => {
    // 4 levels of nesting: {1|{2|{3|{4|end}}}}
    const nested = "{1|{2|{3|{4|deep}}}}"
    expect(validateSpintax(nested).valid).toBe(false)

    const sanitized = sanitizeSpintax(nested)
    expect(validateSpintax(sanitized).valid).toBe(true)
  })

  it("Layer 2: Handles truncation without leaving dangling braces", () => {
    const longText = "a".repeat(MAX_SPINTAX_CHARS - 10) + "{quick|smart|clever}"
    const sanitized = sanitizeSpintax(longText)
    expect(sanitized.length).toBeLessThanOrEqual(MAX_SPINTAX_CHARS)
    expect(validateSpintax(sanitized).valid).toBe(true)
  })
})
