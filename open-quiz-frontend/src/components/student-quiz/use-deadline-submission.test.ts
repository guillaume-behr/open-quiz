// @vitest-environment jsdom
import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { StudentQuizSession } from "@/api/types"

import {
    DEADLINE_SUBMISSION_LEAD_MS,
    hasUnsentAnswer,
    useDeadlineSubmission,
    type EnteredAnswer,
} from "./use-deadline-submission"

function session(
    answerMode: "written" | "single" | "multiple",
    overrides: Partial<StudentQuizSession> = {},
    secondsLeft = 60
): StudentQuizSession {
    const now = Date.now()
    return {
        status: "in_progress",
        server_now: new Date(now).toISOString(),
        ends_at: new Date(now + secondsLeft * 1000).toISOString(),
        question: { id: 7, answer_mode: answerMode },
        selected_choice_ids: null,
        written_answer: null,
        ...overrides,
    } as unknown as StudentQuizSession
}

const written = (text: string): EnteredAnswer => ({
    selectedChoiceIds: [],
    writtenAnswer: text,
})
const chosen = (...ids: string[]): EnteredAnswer => ({
    selectedChoiceIds: ids,
    writtenAnswer: "",
})

describe("hasUnsentAnswer", () => {
    it("is true only for an entered answer the server does not hold", () => {
        expect(hasUnsentAnswer(session("written"), written("Draft"))).toBe(true)
        expect(hasUnsentAnswer(session("written"), written("   "))).toBe(false)
        expect(
            hasUnsentAnswer(
                session("written", { written_answer: "Sent" }),
                written(" Sent ")
            )
        ).toBe(false)
        expect(hasUnsentAnswer(session("multiple"), chosen())).toBe(false)
        expect(hasUnsentAnswer(session("multiple"), chosen("a"))).toBe(true)
        const saved = session("multiple", { selected_choice_ids: ["a", "b"] })
        expect(hasUnsentAnswer(saved, chosen("b", "a"))).toBe(false)
        expect(hasUnsentAnswer(saved, chosen("a"))).toBe(true)
        expect(hasUnsentAnswer(saved, chosen("a", "c"))).toBe(true)
        expect(
            hasUnsentAnswer(session("single", { question: null }), chosen("a"))
        ).toBe(false)
    })
})

describe("useDeadlineSubmission", () => {
    beforeEach(() => vi.useFakeTimers())
    afterEach(() => vi.useRealTimers())

    function watch(
        current: StudentQuizSession,
        entered: EnteredAnswer,
        isBusy = false
    ) {
        const submit = vi.fn()
        const hook = renderHook(
            (props: { session: StudentQuizSession; entered: EnteredAnswer }) =>
                useDeadlineSubmission(
                    props.session,
                    props.entered,
                    isBusy,
                    submit
                ),
            { initialProps: { session: current, entered } }
        )
        return { submit, ...hook }
    }

    it("sends the answer on screen just before the time runs out", () => {
        const { submit, rerender } = watch(session("written"), written("Dr"))
        rerender({ session: session("written"), entered: written("Draft") })
        vi.advanceTimersByTime(60_000 - DEADLINE_SUBMISSION_LEAD_MS - 100)
        expect(submit).not.toHaveBeenCalled()
        vi.advanceTimersByTime(200)
        expect(submit).toHaveBeenCalledOnce()
    })

    it("counts down on the server's clock", () => {
        // The server is 20 seconds behind this computer.
        const behind = session("written")
        const serverTime = Date.parse(behind.server_now ?? "") - 20_000
        const { submit } = watch(
            {
                ...behind,
                server_now: new Date(serverTime).toISOString(),
                ends_at: new Date(serverTime + 30_000).toISOString(),
            },
            written("Draft")
        )
        // On this computer's clock, 10 seconds would be left.
        vi.advanceTimersByTime(20_000)
        expect(submit).not.toHaveBeenCalled()
        vi.advanceTimersByTime(10_000 - DEADLINE_SUBMISSION_LEAD_MS + 100)
        expect(submit).toHaveBeenCalledOnce()
    })

    it("sends nothing already sent, while busy, or once time is up", () => {
        const sent = watch(
            session("written", { written_answer: "Done" }),
            written("Done")
        )
        const busy = watch(session("written"), written("Draft"), true)
        const late = watch(session("written", {}, -1), written("Draft"))
        vi.advanceTimersByTime(120_000)
        expect(sent.submit).not.toHaveBeenCalled()
        expect(busy.submit).not.toHaveBeenCalled()
        expect(late.submit).not.toHaveBeenCalled()
    })

    it("follows the question on screen and stops when unmounted", () => {
        const { submit, rerender, unmount } = watch(
            session("written"),
            written("Draft")
        )
        // A paused exam has no question and no deadline to meet.
        rerender({
            session: session("written", { status: "paused", question: null }),
            entered: written("Draft"),
        })
        vi.advanceTimersByTime(120_000)
        expect(submit).not.toHaveBeenCalled()

        rerender({ session: session("written"), entered: written("Draft") })
        unmount()
        vi.advanceTimersByTime(120_000)
        expect(submit).not.toHaveBeenCalled()
    })
})
