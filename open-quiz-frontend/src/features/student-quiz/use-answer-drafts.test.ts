// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { clearStudentStorage } from "@/lib/student-session-storage"
import { draftKey } from "./answer-drafts"
import {
    type AnswerDrafts,
    DRAFT_SAVE_DELAY_MS,
    useAnswerDrafts,
} from "./use-answer-drafts"

// React warns unless the environment says it supports act().
;(
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null

function mountDrafts(joinCode: string | null): AnswerDrafts {
    let drafts: AnswerDrafts | null = null
    function Probe() {
        drafts = useAnswerDrafts(joinCode)
        return null
    }
    const container = document.createElement("div")
    root = createRoot(container)
    act(() => root?.render(createElement(Probe)))
    if (!drafts) throw new Error("The hook did not render")
    return drafts
}

function unmount() {
    act(() => root?.unmount())
    root = null
}

const typed = { selectedChoiceIds: [], writtenAnswer: "Photosynthesis" }

beforeEach(() => {
    vi.useFakeTimers()
})

afterEach(() => {
    if (root) unmount()
    vi.useRealTimers()
    vi.restoreAllMocks()
    sessionStorage.clear()
})

describe("useAnswerDrafts", () => {
    it("persists a draft after the delay and restores it on a new mount", () => {
        const drafts = mountDrafts("ABCD")
        drafts.setDraft(42, typed)
        expect(sessionStorage.getItem(draftKey("ABCD", 42))).toBeNull()
        vi.advanceTimersByTime(DRAFT_SAVE_DELAY_MS)
        expect(sessionStorage.getItem(draftKey("ABCD", 42))).not.toBeNull()
        unmount()

        expect(mountDrafts("ABCD").getDraft(42)).toEqual(typed)
        // Another exam's drafts are kept apart.
        unmount()
        expect(mountDrafts("WXYZ").getDraft(42)).toBeUndefined()
    })

    it("saves at once when the page is hidden or left", () => {
        const drafts = mountDrafts("ABCD")
        drafts.setDraft(42, typed)
        window.dispatchEvent(new Event("pagehide"))
        expect(sessionStorage.getItem(draftKey("ABCD", 42))).not.toBeNull()
    })

    it("tells an empty draft apart from a missing one", () => {
        const drafts = mountDrafts("ABCD")
        drafts.setDraft(42, { selectedChoiceIds: [], writtenAnswer: "" })
        expect(drafts.getDraft(42)).toEqual({
            selectedChoiceIds: [],
            writtenAnswer: "",
        })
        expect(drafts.getDraft(43)).toBeUndefined()
    })

    it("clears one draft, all drafts, or everything on logout", () => {
        const drafts = mountDrafts("ABCD")
        drafts.setDraft(41, typed)
        drafts.setDraft(42, typed)
        vi.advanceTimersByTime(DRAFT_SAVE_DELAY_MS)

        drafts.clearDraft(41)
        expect(drafts.getDraft(41)).toBeUndefined()
        expect(sessionStorage.getItem(draftKey("ABCD", 41))).toBeNull()

        drafts.clearAll()
        expect(drafts.getDraft(42)).toBeUndefined()
        expect(sessionStorage.getItem(draftKey("ABCD", 42))).toBeNull()

        drafts.setDraft(42, typed)
        vi.advanceTimersByTime(DRAFT_SAVE_DELAY_MS)
        clearStudentStorage()
        expect(sessionStorage.length).toBe(0)
    })

    it("keeps working when sessionStorage throws", () => {
        for (const method of [
            "getItem",
            "setItem",
            "removeItem",
            "key",
        ] as const)
            vi.spyOn(Storage.prototype, method).mockImplementation(() => {
                throw new Error("blocked")
            })
        const drafts = mountDrafts("ABCD")
        drafts.setDraft(42, typed)
        vi.advanceTimersByTime(DRAFT_SAVE_DELAY_MS)
        expect(drafts.getDraft(42)).toEqual(typed)
        unmount()
        // The memory fallback still restores it within this page.
        expect(mountDrafts("ABCD").getDraft(42)).toEqual(typed)
        clearStudentStorage()
    })
})
