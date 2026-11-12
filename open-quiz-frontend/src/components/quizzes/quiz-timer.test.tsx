// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { QuizTimer } from "./quiz-timer"

describe("QuizTimer", () => {
    beforeEach(() => {
        vi.useFakeTimers()
        vi.setSystemTime(new Date("2026-01-01T09:00:00Z"))
    })
    afterEach(() => vi.useRealTimers())

    it("renders nothing without an end", () => {
        const { container } = render(<QuizTimer endsAt={null} />)
        expect(container).toBeEmptyDOMElement()
    })

    it("counts down and announces the minutes left as they are crossed", () => {
        render(<QuizTimer endsAt="2026-01-01T09:05:02Z" />)
        const timer = screen.getByRole("timer")
        expect(timer).toHaveTextContent("5:02")
        act(() => vi.advanceTimersByTime(3000))
        expect(timer).toHaveTextContent("4:59")
        expect(timer).toHaveTextContent('timer-minutes-left {"count":5}')
        act(() => vi.advanceTimersByTime(240_000))
        expect(timer).toHaveTextContent("0:59")
        expect(timer.className).toContain("text-destructive")
    })

    it("follows the server's clock rather than the device's", () => {
        render(
            <QuizTimer
                endsAt="2026-01-01T10:00:00Z"
                serverNow="2026-01-01T09:59:00Z"
                variant="display"
            />
        )
        expect(screen.getByRole("timer")).toHaveTextContent("1:00")
    })
})
