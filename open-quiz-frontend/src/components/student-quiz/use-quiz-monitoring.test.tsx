// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { StudentQuizSession } from "@/api/types"

import { useQuizMonitoring } from "./use-quiz-monitoring"

const api = vi.hoisted(() => ({ reportStudentQuizViolation: vi.fn() }))
vi.mock("@/api/quizzes", () => api)

const running = {
    status: "in_progress",
    join_code: "ABC123",
    question: { id: 1 },
} as unknown as StudentQuizSession

let fullscreen: Element | null = null

function setFullscreen(value: boolean) {
    fullscreen = value ? document.documentElement : null
    document.dispatchEvent(new Event("fullscreenchange"))
}

function reported(): string[] {
    return api.reportStudentQuizViolation.mock.calls.map((call) => call[2])
}

describe("useQuizMonitoring", () => {
    beforeEach(() => {
        vi.useFakeTimers()
        fullscreen = null
        // jsdom implements no fullscreen API.
        Object.defineProperty(document, "fullscreenElement", {
            configurable: true,
            get: () => fullscreen,
        })
        api.reportStudentQuizViolation.mockResolvedValue(undefined)
    })
    afterEach(() => vi.useRealTimers())

    function monitor(leaving = false) {
        return renderHook(
            ({ session }) =>
                useQuizMonitoring(session, "token", { current: leaving }),
            { initialProps: { session: running as StudentQuizSession | null } }
        )
    }

    it("reports nothing during the grace period after entering fullscreen", () => {
        monitor()
        act(() => setFullscreen(true))
        window.dispatchEvent(new Event("blur"))
        expect(reported()).toEqual([])
        vi.advanceTimersByTime(1500)
        window.dispatchEvent(new Event("blur"))
        expect(reported()).toEqual(["window_blur"])
        // The same violation is not reported twice within the grace period.
        window.dispatchEvent(new Event("blur"))
        expect(reported()).toEqual(["window_blur"])
    })

    it("reports each kind of violation once armed", () => {
        monitor()
        act(() => setFullscreen(true))
        vi.advanceTimersByTime(2000)
        document.documentElement.dispatchEvent(new Event("mouseleave"))
        document.dispatchEvent(new Event("contextmenu"))
        window.dispatchEvent(new Event("beforeprint"))
        vi.spyOn(document, "hidden", "get").mockReturnValue(false)
        document.dispatchEvent(new Event("visibilitychange"))
        vi.spyOn(document, "hidden", "get").mockReturnValue(true)
        document.dispatchEvent(new Event("visibilitychange"))
        act(() => setFullscreen(false))
        expect(reported()).toEqual([
            "pointer_exit",
            "context_menu",
            "print_attempt",
            "page_hidden",
            "fullscreen_exit",
        ])
        // Outside fullscreen only leaving fullscreen counts.
        vi.advanceTimersByTime(2000)
        window.dispatchEvent(new Event("blur"))
        expect(reported()).toHaveLength(5)
    })

    it("stays silent when leaving the quiz, unmonitored or unmounted", () => {
        const { rerender, unmount } = monitor(true)
        act(() => setFullscreen(true))
        vi.advanceTimersByTime(2000)
        window.dispatchEvent(new Event("blur"))
        expect(reported()).toEqual([])

        rerender({ session: null })
        window.dispatchEvent(new Event("blur"))
        unmount()
        window.dispatchEvent(new Event("blur"))
        expect(reported()).toEqual([])
    })

    it("swallows a failed report and enters fullscreen on request", async () => {
        api.reportStudentQuizViolation.mockRejectedValue(new Error("offline"))
        const requestFullscreen = vi.fn(() => Promise.resolve())
        document.documentElement.requestFullscreen = requestFullscreen
        const { result } = monitor()
        await act(() => result.current.enterFullscreen())
        expect(requestFullscreen).toHaveBeenCalled()
        expect(result.current.isFullscreen).toBe(true)
        fullscreen = document.documentElement
        vi.advanceTimersByTime(2000)
        window.dispatchEvent(new Event("blur"))
        expect(reported()).toEqual(["window_blur"])
    })
})
