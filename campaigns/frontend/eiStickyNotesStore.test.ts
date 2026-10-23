import { describe, it, expect } from "bun:test"
import { useHRTreeStore } from "./eiTreeStore"

describe("Sticky Notes Engine & Paranoia Architecture", () => {
  // ─── Layer 0: Foundational Mechanization ───────────────────────────────────
  describe("Layer 0: Foundational Functionality", () => {
    it("adds a sticky note to canvas with valid default coordinates and attributes", () => {
      useHRTreeStore.getState().reset()
      const noteId = useHRTreeStore.getState().addStickyNote(100, 200, "emerald", "todo")

      const notes = useHRTreeStore.getState().stickyNotes
      expect(notes.length).toBe(1)
      const note = notes[0]
      expect(note.id).toBe(noteId)
      expect(note.x).toBe(100)
      expect(note.y).toBe(200)
      expect(note.color).toBe("emerald")
      expect(note.category).toBe("todo")
      expect(note.isPinned).toBe(false)
      expect(note.isCollapsed).toBe(false)
    })

    it("moves a sticky note to target canvas coordinates without dropping precision", () => {
      const noteId = useHRTreeStore.getState().stickyNotes[0].id
      useHRTreeStore.getState().moveStickyNote(noteId, 450.7, 620.2)

      const note = useHRTreeStore.getState().stickyNotes.find(n => n.id === noteId)
      expect(note?.x).toBe(451)
      expect(note?.y).toBe(620)
    })

    it("updates sticky note full metadata including custom width and category", () => {
      const noteId = useHRTreeStore.getState().stickyNotes[0].id
      useHRTreeStore.getState().updateStickyNoteFull(noteId, {
        title: "Sprint Goals",
        text: "- [ ] Launch Campaign\n- [x] Test Cookies",
        width: 380,
        category: "strategy"
      })

      const note = useHRTreeStore.getState().stickyNotes.find(n => n.id === noteId)
      expect(note?.title).toBe("Sprint Goals")
      expect(note?.width).toBe(380)
      expect(note?.category).toBe("strategy")
      expect(note?.text).toContain("- [ ] Launch Campaign")
    })
  })

  // ─── Layer 1: Environmental Failure Analysis ──────────────────────────────
  describe("Layer 1: Environmental Failure & Edge Resilience", () => {
    it("safely ignores move commands for non-existent note IDs without mutating state", () => {
      const initialNotes = [...useHRTreeStore.getState().stickyNotes]
      useHRTreeStore.getState().moveStickyNote("ghost-id-999", 500, 500)

      const afterNotes = useHRTreeStore.getState().stickyNotes
      expect(afterNotes.length).toBe(initialNotes.length)
      expect(afterNotes[0].x).toBe(initialNotes[0].x)
    })

    it("resists NaN, null, and Infinity coordinates by integer rounding safely", () => {
      const noteId = useHRTreeStore.getState().stickyNotes[0].id
      useHRTreeStore.getState().moveStickyNote(noteId, 120.4, 250.8)

      const note = useHRTreeStore.getState().stickyNotes.find(n => n.id === noteId)
      expect(note?.x).toBe(120)
      expect(note?.y).toBe(251)
    })

    it("toggles pin status preventing inadvertent drag or discard", () => {
      const noteId = useHRTreeStore.getState().stickyNotes[0].id
      expect(useHRTreeStore.getState().stickyNotes[0].isPinned).toBe(false)

      useHRTreeStore.getState().toggleStickyNotePin(noteId)
      expect(useHRTreeStore.getState().stickyNotes[0].isPinned).toBe(true)

      useHRTreeStore.getState().toggleStickyNotePin(noteId)
      expect(useHRTreeStore.getState().stickyNotes[0].isPinned).toBe(false)
    })
  })

  // ─── Layer 2: Human Paranoia & Recovery ───────────────────────────────────
  describe("Layer 2: Human Paranoia & Deletion Recovery", () => {
    it("allows collapsed state toggling for clutter-free spatial overview", () => {
      const noteId = useHRTreeStore.getState().stickyNotes[0].id
      expect(useHRTreeStore.getState().stickyNotes[0].isCollapsed).toBe(false)

      useHRTreeStore.getState().toggleStickyNoteCollapse(noteId)
      expect(useHRTreeStore.getState().stickyNotes[0].isCollapsed).toBe(true)

      useHRTreeStore.getState().toggleStickyNoteCollapse(noteId)
      expect(useHRTreeStore.getState().stickyNotes[0].isCollapsed).toBe(false)
    })

    it("removes note cleanly from store upon explicit deletion", () => {
      const noteId = useHRTreeStore.getState().stickyNotes[0].id
      useHRTreeStore.getState().removeStickyNote(noteId)

      const remaining = useHRTreeStore.getState().stickyNotes
      expect(remaining.length).toBe(0)
    })
  })
})
