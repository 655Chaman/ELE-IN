import { useEffect, useRef, useCallback } from "react"

export interface UseModalTrapOptions<TStep extends string = string> {
  isOpen: boolean
  onClose: () => void
  
  // Step / Tab Navigation
  steps?: readonly TStep[] | TStep[]
  currentStep?: TStep
  onStepChange?: (step: TStep) => void
  
  // Primary Form Submission
  onSubmit?: () => void | Promise<void>
  
  // Guard & Paranoia Controls
  isLoading?: boolean
  isSubmitting?: boolean
  hasNestedModal?: boolean
  isDirty?: boolean | (() => boolean)
  onDirtyDismissPrevented?: () => void
  
  // Focus Configuration
  initialFocusRef?: React.RefObject<HTMLElement | null>
  preventBodyScroll?: boolean
  enableTablistNavigation?: boolean
}

const FOCUSABLE_SELECTOR = [
  'button:not([disabled]):not([aria-hidden="true"])',
  '[href]:not([aria-hidden="true"])',
  'input:not([disabled]):not([type="hidden"]):not([aria-hidden="true"])',
  'select:not([disabled]):not([aria-hidden="true"])',
  'textarea:not([disabled]):not([aria-hidden="true"])',
  '[tabindex]:not([tabindex="-1"]):not([disabled]):not([aria-hidden="true"])',
].join(", ")

function isElementVisible(el: HTMLElement): boolean {
  if (el.getAttribute("aria-hidden") === "true") return false
  if (el.hasAttribute("disabled")) return false
  const style = window.getComputedStyle(el)
  if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") {
    return false
  }
  return el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0
}

function isTextInputElement(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false
  const tagName = target.tagName.toUpperCase()
  return (
    tagName === "INPUT" ||
    tagName === "TEXTAREA" ||
    target.isContentEditable ||
    target.getAttribute("role") === "textbox"
  )
}

export function useModalTrapAndStepper<TStep extends string = string>({
  isOpen,
  onClose,
  steps,
  currentStep,
  onStepChange,
  onSubmit,
  isLoading = false,
  isSubmitting = false,
  hasNestedModal = false,
  isDirty = false,
  onDirtyDismissPrevented,
  initialFocusRef,
  preventBodyScroll = true,
  enableTablistNavigation = true,
}: UseModalTrapOptions<TStep>) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const previousActiveElement = useRef<HTMLElement | null>(null)
  const lastEscapePressRef = useRef<number>(0)
  const isExecutingSubmitRef = useRef<boolean>(false)

  // 1. Capture and restore previously active element + lock body scroll
  useEffect(() => {
    if (!isOpen) {
      // Modal just closed or unmounted: restore focus gracefully
      if (
        previousActiveElement.current &&
        document.contains(previousActiveElement.current) &&
        typeof previousActiveElement.current.focus === "function"
      ) {
        previousActiveElement.current.focus({ preventScroll: true })
      } else {
        // Fallback target: prevent focus dropping to <body> and causing scroll jumping
        const fallbackTarget = document.getElementById("main-content") || document.querySelector("main")
        if (fallbackTarget && typeof fallbackTarget.focus === "function") {
          fallbackTarget.focus({ preventScroll: true })
        }
      }
      previousActiveElement.current = null
      return
    }

    // Modal just opened: save active element before focusing inside modal
    const active = document.activeElement as HTMLElement | null
    if (active && (!containerRef.current || !containerRef.current.contains(active))) {
      previousActiveElement.current = active
    }

    const originalOverflow = document.body.style.overflow
    if (preventBodyScroll) {
      document.body.style.overflow = "hidden"
    }

    // Set Initial Focus with microtask delay
    const timer = setTimeout(() => {
      if (initialFocusRef?.current) {
        initialFocusRef.current.focus()
      } else if (containerRef.current) {
        const focusable = Array.from(
          containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        ).filter(isElementVisible)

        if (focusable.length > 0) {
          focusable[0].focus()
        } else {
          containerRef.current.focus()
        }
      }
    }, 40)

    return () => {
      clearTimeout(timer)
      if (preventBodyScroll) {
        document.body.style.overflow = originalOverflow
      }
    }
  }, [isOpen, initialFocusRef, preventBodyScroll])

  // 2. Comprehensive Keyboard Handler
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen || !containerRef.current) return

      // Layer 0 Paranoia: If a sub-dialog is active, pause parent trap
      if (hasNestedModal) return

      // ── ESCAPE HANDLING & HIERARCHICAL DISMISSAL ──
      if (e.key === "Escape") {
        // A. If already handled by an inner element, stop
        if (e.defaultPrevented) return

        // B. Radix Portal & Select / Popover Check:
        // Do not close parent modal if a Radix select dropdown or popover is open
        const hasOpenRadixOverlay = Boolean(
          document.querySelector(
            '[data-radix-popper-content-wrapper], [data-radix-select-viewport], [role="listbox"][data-state="open"], [data-state="open"][data-radix-menu-content]'
          )
        )
        if (hasOpenRadixOverlay) {
          return // Let Radix handle dismissing the dropdown
        }

        // C. Network In-Flight Lock:
        if (isLoading || isSubmitting) {
          e.preventDefault()
          e.stopPropagation()
          return
        }

        // D. Layer 2 Human Paranoia: Double-Tap Escape on Dirty Form
        const dirty = typeof isDirty === "function" ? isDirty() : isDirty
        if (dirty) {
          const now = Date.now()
          if (now - lastEscapePressRef.current > 2000) {
            // First escape press: block and warn
            lastEscapePressRef.current = now
            e.preventDefault()
            e.stopPropagation()
            onDirtyDismissPrevented?.()
            return
          }
          // Second escape press within 2s: proceed with dismissal
        }

        e.preventDefault()
        e.stopPropagation()
        onClose()
        return
      }

      // ── PRIMARY SUBMIT SHORTCUT (Cmd+Enter on Mac, Ctrl+Enter on Win/Linux) ──
      const isPrimaryModifier = e.metaKey || (e.ctrlKey && !e.altKey)
      if (isPrimaryModifier && e.key === "Enter") {
        if (onSubmit && !isLoading && !isSubmitting && !isExecutingSubmitRef.current) {
          e.preventDefault()
          e.stopPropagation()
          isExecutingSubmitRef.current = true
          Promise.resolve(onSubmit()).finally(() => {
            isExecutingSubmitRef.current = false
          })
          return
        }
      }

      // ── STEPPER SHORTCUTS (Cmd+1..9 or Alt+1..9) ──
      // AltGr Protection: On European keyboards, AltGr emits ctrlKey + altKey.
      const isAltGr = e.ctrlKey && e.altKey
      const isStepModifier = (e.metaKey || e.altKey) && !isAltGr

      if (steps && steps.length > 0 && onStepChange && isStepModifier) {
        // Paranoia Layer 1: Never hijack numbers if user is typing in a form input or textarea
        if (!isTextInputElement(e.target)) {
          const num = parseInt(e.key, 10)
          if (!isNaN(num) && num >= 1 && num <= steps.length) {
            e.preventDefault()
            e.stopPropagation()
            onStepChange(steps[num - 1])
            return
          }
        }
      }

      // ── W3C APG TABLIST ARROW NAVIGATION ──
      if (enableTablistNavigation && steps && steps.length > 0 && onStepChange) {
        const activeEl = document.activeElement as HTMLElement | null
        if (activeEl && activeEl.getAttribute("role") === "tab") {
          let targetIndex = -1
          const currentIndex = currentStep ? steps.indexOf(currentStep) : -1

          if (e.key === "ArrowRight" || e.key === "ArrowDown") {
            e.preventDefault()
            targetIndex = currentIndex < steps.length - 1 ? currentIndex + 1 : 0
          } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
            e.preventDefault()
            targetIndex = currentIndex > 0 ? currentIndex - 1 : steps.length - 1
          } else if (e.key === "Home") {
            e.preventDefault()
            targetIndex = 0
          } else if (e.key === "End") {
            e.preventDefault()
            targetIndex = steps.length - 1
          }

          if (targetIndex >= 0) {
            onStepChange(steps[targetIndex])
            // Focus new tab element after DOM update
            requestAnimationFrame(() => {
              const tablist = activeEl.closest('[role="tablist"]')
              const tabs = tablist?.querySelectorAll<HTMLElement>('[role="tab"]')
              tabs?.[targetIndex]?.focus()
            })
            return
          }
        }
      }

      // ── FOCUS TRAPPING (Tab / Shift+Tab) ──
      if (e.key === "Tab") {
        // If focus is currently inside an open Radix portal outside container, let Radix cycle
        const activeEl = document.activeElement as HTMLElement | null
        const isInsideRadixPortal = Boolean(
          activeEl?.closest(
            '[data-radix-popper-content-wrapper], [data-radix-select-viewport], [role="listbox"]'
          )
        )
        if (isInsideRadixPortal) {
          return
        }

        const focusable = Array.from(
          containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        ).filter(isElementVisible)

        if (focusable.length === 0) {
          e.preventDefault()
          return
        }

        const first = focusable[0]
        const last = focusable[focusable.length - 1]

        // If focus escaped completely outside container, reset it immediately
        if (!activeEl || !containerRef.current.contains(activeEl)) {
          e.preventDefault()
          if (e.shiftKey) {
            last.focus()
          } else {
            first.focus()
          }
          return
        }

        if (e.shiftKey) {
          if (activeEl === first) {
            e.preventDefault()
            last.focus()
          }
        } else {
          if (activeEl === last) {
            e.preventDefault()
            first.focus()
          }
        }
      }
    },
    [
      isOpen,
      onClose,
      steps,
      currentStep,
      onStepChange,
      onSubmit,
      isLoading,
      isSubmitting,
      hasNestedModal,
      isDirty,
      onDirtyDismissPrevented,
      enableTablistNavigation,
    ]
  )

  useEffect(() => {
    if (!isOpen) return
    window.addEventListener("keydown", handleKeyDown, true)
    return () => window.removeEventListener("keydown", handleKeyDown, true)
  }, [isOpen, handleKeyDown])

  useEffect(() => {
    return () => {
      // Final unmount cleanup: restore focus to trigger or main landmark if unmounted while open
      if (
        previousActiveElement.current &&
        document.contains(previousActiveElement.current) &&
        typeof previousActiveElement.current.focus === "function"
      ) {
        previousActiveElement.current.focus({ preventScroll: true })
      }
    }
  }, [])

  return {
    containerRef,
    handleBackdropClick: (e: React.MouseEvent) => {
      if (e.target !== e.currentTarget) return
      if (isLoading || isSubmitting) return

      const dirty = typeof isDirty === "function" ? isDirty() : isDirty
      if (dirty) {
        onDirtyDismissPrevented?.()
        return
      }
      onClose()
    },
  }
}
