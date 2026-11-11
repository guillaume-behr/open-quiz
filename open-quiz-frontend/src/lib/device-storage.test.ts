// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import { clearOpenQuizStorage } from "@/lib/device-storage"

afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    sessionStorage.clear()
})

describe("clearOpenQuizStorage", () => {
    it("removes every Open Quiz key and preference, and nothing else", () => {
        localStorage.setItem("open-quiz-teacher-results-view", "cards")
        localStorage.setItem("open-quiz-session-display:quiz-4", "{}")
        localStorage.setItem("i18nextLng", "fr")
        localStorage.setItem("vite-ui-theme", "dark")
        localStorage.setItem("another-site-key", "kept")
        sessionStorage.setItem("open-quiz-refresh-proof", "proof")
        sessionStorage.setItem("open-quiz-module-reload-at", "1")
        sessionStorage.setItem("open-quiz-student-access-token", "token")

        expect(clearOpenQuizStorage()).toBe(true)

        expect(Object.keys(localStorage)).toEqual(["another-site-key"])
        expect(Object.keys(sessionStorage)).toEqual([])
    })

    it("reports storage the browser refuses", () => {
        vi.spyOn(Storage.prototype, "key").mockImplementation(() => {
            throw new Error("blocked")
        })
        localStorage.setItem("open-quiz-x", "1")
        expect(clearOpenQuizStorage()).toBe(false)
    })
})
