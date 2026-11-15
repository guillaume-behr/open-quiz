// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react"
import type { FormEvent } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/api/client"
import type { StudentQuizSession } from "@/api/types"

import {
    ANSWER_SAVE_DELAY_MS,
    useStudentQuizSession,
} from "./use-student-quiz-session"

const api = vi.hoisted(() => ({
    getStudentQuizSession: vi.fn(),
    joinQuiz: vi.fn(),
    leaveStudentQuiz: vi.fn(),
    navigateStudentQuiz: vi.fn(),
    reviewStudentAnswers: vi.fn(),
    saveStudentQuizAnswer: vi.fn(),
    skipStudentQuestion: vi.fn(),
    submitStudentQuiz: vi.fn(),
    submitStudentQuizAnswer: vi.fn(),
}))
vi.mock("@/api/quizzes", () => api)

const stored = vi.hoisted(() => ({
    readStoredQuizSession: vi.fn(),
    storeQuizSession: vi.fn(),
    clearStoredQuizSession: vi.fn(),
}))
vi.mock("./student-quiz-session", () => stored)

const live = vi.hoisted(() => ({
    connectLiveUpdates: vi.fn(),
}))
vi.mock("@/lib/live-updates", () => live)

const navigate = vi.hoisted(() => vi.fn())
vi.mock("react-router", () => ({ useNavigate: () => navigate }))

type LiveOptions = {
    onData: (session: StudentQuizSession) => void
    onUnavailable: () => void
    onConnectionChange: (state: string) => void
}

function quizSession(
    overrides: Partial<StudentQuizSession> = {}
): StudentQuizSession {
    return {
        join_code: "ABC123",
        status: "running",
        accessible_question_numbers: [1, 2],
        question: { id: 1, answer_mode: "single" },
        selected_choice_ids: [],
        written_answer: null,
        ...overrides,
    } as unknown as StudentQuizSession
}

function formEvent() {
    return {
        preventDefault: vi.fn(),
    } as unknown as FormEvent<HTMLFormElement>
}

function liveOptions(): LiveOptions {
    const calls = live.connectLiveUpdates.mock.calls
    const options = calls[calls.length - 1]?.[0] as LiveOptions | undefined
    if (!options) throw new Error("no live connection")
    return options
}

async function joined() {
    api.joinQuiz.mockResolvedValue({
        ...quizSession(),
        participant_token: "participant",
    })
    const onSessionCleared = vi.fn()
    const hook = renderHook(() =>
        useStudentQuizSession("student", onSessionCleared)
    )
    act(() => hook.result.current.updateJoinCode(" abc123 "))
    await act(() => hook.result.current.join(formEvent()))
    return { hook, onSessionCleared }
}

describe("useStudentQuizSession", () => {
    beforeEach(() => {
        vi.clearAllMocks()
        sessionStorage.clear()
        stored.readStoredQuizSession.mockReturnValue(null)
        live.connectLiveUpdates.mockReturnValue(() => undefined)
    })

    it("sends the answer on screen just before the exam's time runs out", async () => {
        vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] })
        try {
            const now = Date.now()
            api.joinQuiz.mockResolvedValue({
                ...quizSession({
                    status: "in_progress",
                    server_now: new Date(now).toISOString(),
                    ends_at: new Date(now + 60_000).toISOString(),
                    question: { id: 1, answer_mode: "written" } as never,
                }),
                participant_token: "participant",
            })
            api.submitStudentQuizAnswer.mockResolvedValue(
                quizSession({ status: "finished", question: null })
            )
            const hook = renderHook(() => useStudentQuizSession("student"))
            act(() => hook.result.current.updateJoinCode("ABC123"))
            await act(() => hook.result.current.join(formEvent()))
            act(() => hook.result.current.setWrittenAnswer("Half of my answer"))

            await act(() => vi.advanceTimersByTimeAsync(59_000))

            expect(api.submitStudentQuizAnswer).toHaveBeenCalledWith(
                "ABC123",
                "participant",
                {
                    question_id: 1,
                    selected_choice_ids: undefined,
                    written_answer: "Half of my answer",
                }
            )
        } finally {
            vi.useRealTimers()
        }
    })

    it("joins an exam, stores it and opens its live connection", async () => {
        const { hook } = await joined()

        expect(api.joinQuiz).toHaveBeenCalledWith("abc123", "student")
        expect(stored.storeQuizSession).toHaveBeenCalledWith({
            joinCode: "ABC123",
            participantToken: "participant",
        })
        expect(hook.result.current.session?.join_code).toBe("ABC123")
        expect(hook.result.current.participantToken).toBe("participant")
        expect(live.connectLiveUpdates).toHaveBeenCalledTimes(1)
    })

    it("shows why joining failed", async () => {
        api.joinQuiz.mockRejectedValue(new Error("down"))
        const { result } = renderHook(() => useStudentQuizSession("student"))

        await act(() => result.current.join(formEvent()))

        expect(result.current.error).toBe("join-quiz-error")
        expect(result.current.isBusy).toBe(false)
    })

    it("restores the stored session", async () => {
        stored.readStoredQuizSession.mockReturnValue({
            joinCode: "ABC123",
            participantToken: "participant",
        })
        api.getStudentQuizSession.mockResolvedValue(
            quizSession({ selected_choice_ids: ["a"] })
        )

        const { result } = renderHook(() => useStudentQuizSession("student"))

        await waitFor(() => expect(result.current.session).not.toBeNull())
        expect(result.current.selectedChoiceIds).toEqual(["a"])
    })

    it("forgets a stored session the server no longer knows", async () => {
        stored.readStoredQuizSession.mockReturnValue({
            joinCode: "ABC123",
            participantToken: "participant",
        })
        api.getStudentQuizSession.mockRejectedValue(
            new ApiError("gone", 404, {})
        )
        const onSessionCleared = vi.fn()

        const { result } = renderHook(() =>
            useStudentQuizSession("student", onSessionCleared)
        )

        await waitFor(() =>
            expect(result.current.error).toBe("student-session-restore-error")
        )
        expect(stored.clearStoredQuizSession).toHaveBeenCalled()
        expect(result.current.participantToken).toBeNull()
        expect(onSessionCleared).toHaveBeenCalled()
    })

    it("says when the exam was resumed in another window", async () => {
        stored.readStoredQuizSession.mockReturnValue({
            joinCode: "ABC123",
            participantToken: "participant",
        })
        api.getStudentQuizSession.mockRejectedValue(
            new ApiError("resumed", 409, {
                code: "QUIZ_PARTICIPANT_SESSION_RESUMED",
            })
        )
        const onSessionCleared = vi.fn()

        const { result } = renderHook(() =>
            useStudentQuizSession("student", onSessionCleared)
        )

        await waitFor(() => expect(result.current.error).not.toBeNull())
        expect(result.current.error).not.toBe("student-session-restore-error")
        expect(onSessionCleared).not.toHaveBeenCalled()
    })

    it("navigates, reviews and hands in the exam", async () => {
        const { hook } = await joined()
        api.navigateStudentQuiz.mockResolvedValue(
            quizSession({ question: { id: 2 } as never })
        )
        await act(() => hook.result.current.goToQuestion(2))
        expect(api.navigateStudentQuiz).toHaveBeenCalledWith(
            "ABC123",
            "participant",
            2
        )
        expect(hook.result.current.session?.question?.id).toBe(2)

        // A question that cannot be opened sends nothing.
        await act(() => hook.result.current.goToQuestion(5))
        expect(api.navigateStudentQuiz).toHaveBeenCalledTimes(1)

        api.reviewStudentAnswers.mockResolvedValue(
            quizSession({ question: null })
        )
        await act(() => hook.result.current.backToReview())
        expect(hook.result.current.session?.question).toBeNull()

        api.submitStudentQuiz.mockResolvedValue(
            quizSession({ status: "finished", question: null })
        )
        await act(() => hook.result.current.submitQuiz())
        expect(hook.result.current.session?.status).toBe("finished")
    })

    it("reports a failed request with its own message", async () => {
        const { hook } = await joined()
        api.reviewStudentAnswers.mockRejectedValue(new Error("down"))
        await act(() => hook.result.current.backToReview())
        expect(hook.result.current.error).toBe("student-navigation-error")

        api.submitStudentQuiz.mockRejectedValue(new Error("down"))
        await act(() => hook.result.current.submitQuiz())
        expect(hook.result.current.error).toBe("student-submit-quiz-error")
        expect(hook.result.current.isBusy).toBe(false)
    })

    it("keeps the live state when it arrives before the reply", async () => {
        const { hook } = await joined()
        let resolve: (value: StudentQuizSession) => void = () => undefined
        api.navigateStudentQuiz.mockReturnValue(
            new Promise<StudentQuizSession>((done) => {
                resolve = done
            })
        )

        let pending: Promise<void> = Promise.resolve()
        act(() => {
            pending = hook.result.current.goToQuestion(2)
        })
        act(() => liveOptions().onData(quizSession({ status: "paused" })))
        await act(async () => {
            resolve(quizSession({ question: { id: 2 } as never }))
            await pending
        })

        expect(hook.result.current.session?.status).toBe("paused")
        expect(hook.result.current.session?.question?.id).toBe(1)
    })

    it("submits the answer entered and reports the live connection", async () => {
        const { hook } = await joined()
        act(() => hook.result.current.setSelectedChoiceIds(["b"]))
        api.submitStudentQuizAnswer.mockResolvedValue(
            quizSession({ question: { id: 2 } as never })
        )

        await act(() => hook.result.current.submitAnswer(formEvent()))

        expect(api.submitStudentQuizAnswer).toHaveBeenCalledWith(
            "ABC123",
            "participant",
            {
                question_id: 1,
                selected_choice_ids: ["b"],
                written_answer: undefined,
            }
        )

        act(() => liveOptions().onConnectionChange("reconnecting"))
        expect(hook.result.current.liveReconnecting).toBe(true)
        act(() => liveOptions().onUnavailable())
        expect(hook.result.current.error).toBe("student-session-error")
    })

    it("reloads the current question when the answer was for another", async () => {
        const { hook } = await joined()
        api.submitStudentQuizAnswer.mockRejectedValue(
            new ApiError("mismatch", 409, { code: "ANSWER_QUESTION_MISMATCH" })
        )
        api.getStudentQuizSession.mockResolvedValue(
            quizSession({ question: { id: 3 } as never })
        )

        await act(() => hook.result.current.submitAnswer(formEvent()))

        expect(hook.result.current.session?.question?.id).toBe(3)
        expect(hook.result.current.error).not.toBeNull()
    })

    it("skips the current question, or reloads it when it was another", async () => {
        const { hook } = await joined()
        api.skipStudentQuestion.mockResolvedValueOnce(
            quizSession({ question: { id: 2 } as never })
        )

        await act(() => hook.result.current.skipQuestion())

        expect(api.skipStudentQuestion).toHaveBeenCalledWith(
            "ABC123",
            "participant",
            1
        )
        expect(hook.result.current.session?.question?.id).toBe(2)

        api.skipStudentQuestion.mockRejectedValueOnce(
            new ApiError("mismatch", 409, { code: "ANSWER_QUESTION_MISMATCH" })
        )
        api.getStudentQuizSession.mockResolvedValue(
            quizSession({ question: { id: 3 } as never })
        )
        await act(() => hook.result.current.skipQuestion())
        expect(hook.result.current.session?.question?.id).toBe(3)
    })

    it("keeps what was entered when the question is skipped", async () => {
        const { hook } = await joined()
        act(() => hook.result.current.setSelectedChoiceIds(["b"]))
        api.skipStudentQuestion.mockResolvedValue(
            quizSession({ question: { id: 2 } as never })
        )

        await act(() => hook.result.current.skipQuestion())
        expect(hook.result.current.selectedChoiceIds).toEqual([])

        // Coming back to the skipped question shows the draft again.
        act(() => liveOptions().onData(quizSession()))
        expect(hook.result.current.selectedChoiceIds).toEqual(["b"])
    })

    it("leaves the exam and clears what it kept", async () => {
        const { hook, onSessionCleared } = await joined()
        api.leaveStudentQuiz.mockResolvedValue(undefined)
        const resetView = vi.fn()

        await act(() => hook.result.current.leave(resetView))

        expect(stored.clearStoredQuizSession).toHaveBeenCalled()
        expect(hook.result.current.session).toBeNull()
        expect(hook.result.current.joinCode).toBe("")
        expect(resetView).toHaveBeenCalled()
        expect(onSessionCleared).toHaveBeenCalled()
        expect(navigate).not.toHaveBeenCalled()
    })

    it("stays in the exam when leaving fails", async () => {
        const { hook } = await joined()
        api.leaveStudentQuiz.mockRejectedValue(new Error("down"))

        await act(() => hook.result.current.leave(vi.fn()))

        expect(hook.result.current.session).not.toBeNull()
        expect(hook.result.current.error).toBe("student-session-error")
        expect(hook.result.current.isLeavingQuiz.current).toBe(false)
    })

    // An exam the student may go back in, on its first question of two.
    function examSession(overrides: Partial<StudentQuizSession> = {}) {
        return quizSession({
            status: "in_progress",
            allow_previous_questions: true,
            question_number: 1,
            total_questions: 2,
            answered_question_numbers: [],
            skipped_question_numbers: [],
            ...overrides,
        })
    }

    async function joinedExam(overrides: Partial<StudentQuizSession> = {}) {
        api.joinQuiz.mockResolvedValue({
            ...examSession(overrides),
            participant_token: "participant",
        })
        const hook = renderHook(() => useStudentQuizSession("student"))
        act(() => hook.result.current.updateJoinCode("ABC123"))
        await act(() => hook.result.current.join(formEvent()))
        return hook
    }

    it("saves a change to a question already answered by itself", async () => {
        vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
        try {
            const hook = await joinedExam({
                answered_question_numbers: [1],
                selected_choice_ids: ["a"],
            })
            expect(hook.result.current.offersNextQuestion).toBe(true)
            api.saveStudentQuizAnswer.mockResolvedValue(
                examSession({
                    answered_question_numbers: [1],
                    selected_choice_ids: ["b"],
                })
            )

            act(() => hook.result.current.setSelectedChoiceIds(["b"]))
            await act(() =>
                vi.advanceTimersByTimeAsync(ANSWER_SAVE_DELAY_MS - 1)
            )
            expect(api.saveStudentQuizAnswer).not.toHaveBeenCalled()
            await act(() => vi.advanceTimersByTimeAsync(1))

            expect(api.saveStudentQuizAnswer).toHaveBeenCalledExactlyOnceWith(
                "ABC123",
                "participant",
                { question_id: 1, selected_choice_ids: ["b"] }
            )
            // Saved: nothing more is sent, and the screen keeps the answer.
            await act(() =>
                vi.advanceTimersByTimeAsync(ANSWER_SAVE_DELAY_MS * 2)
            )
            expect(api.saveStudentQuizAnswer).toHaveBeenCalledTimes(1)
            expect(hook.result.current.selectedChoiceIds).toEqual(["b"])
        } finally {
            vi.useRealTimers()
        }
    })

    it("leaves a question unanswered as it is until the student moves on", async () => {
        vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
        try {
            const hook = await joinedExam()
            expect(hook.result.current.offersNextQuestion).toBe(false)
            act(() => hook.result.current.setSelectedChoiceIds(["a"]))
            await act(() =>
                vi.advanceTimersByTimeAsync(ANSWER_SAVE_DELAY_MS * 2)
            )
            expect(api.saveStudentQuizAnswer).not.toHaveBeenCalled()
        } finally {
            vi.useRealTimers()
        }
    })

    it("saves the answer on screen before going to another question", async () => {
        const hook = await joinedExam({
            question_number: 2,
            question: { id: 2, answer_mode: "written" } as never,
            answered_question_numbers: [1],
        })
        api.saveStudentQuizAnswer.mockResolvedValue(
            examSession({
                question_number: 2,
                question: { id: 2, answer_mode: "written" } as never,
                answered_question_numbers: [1, 2],
                written_answer: "Draft",
            })
        )
        api.navigateStudentQuiz.mockResolvedValue(
            examSession({ answered_question_numbers: [1, 2] })
        )

        act(() => hook.result.current.setWrittenAnswer("Draft"))
        await act(() => hook.result.current.goToQuestion(1))

        expect(api.saveStudentQuizAnswer).toHaveBeenCalledWith(
            "ABC123",
            "participant",
            { question_id: 2, written_answer: "Draft" }
        )
        expect(
            api.saveStudentQuizAnswer.mock.invocationCallOrder[0]
        ).toBeLessThan(api.navigateStudentQuiz.mock.invocationCallOrder[0] ?? 0)
        expect(hook.result.current.session?.question_number).toBe(1)
    })

    it("stays on the question when its answer cannot be saved", async () => {
        const hook = await joinedExam({ answered_question_numbers: [1] })
        api.saveStudentQuizAnswer.mockRejectedValue(new Error("offline"))

        act(() => hook.result.current.setSelectedChoiceIds(["a"]))
        await act(() => hook.result.current.goToNextQuestion())

        expect(api.navigateStudentQuiz).not.toHaveBeenCalled()
        expect(hook.result.current.error).toBe("student-answer-error")
        expect(hook.result.current.isBusy).toBe(false)
    })

    it("goes to the next question without a request when nothing changed", async () => {
        const hook = await joinedExam({
            answered_question_numbers: [1],
            selected_choice_ids: ["a"],
        })
        api.navigateStudentQuiz.mockResolvedValue(
            examSession({ question_number: 2, answered_question_numbers: [1] })
        )

        await act(() => hook.result.current.goToNextQuestion())

        expect(api.saveStudentQuizAnswer).not.toHaveBeenCalled()
        expect(api.navigateStudentQuiz).toHaveBeenCalledWith(
            "ABC123",
            "participant",
            2
        )
    })

    it("offers to submit, not to move on, on the last question", async () => {
        const hook = await joinedExam({
            question_number: 2,
            answered_question_numbers: [1, 2],
        })
        expect(hook.result.current.offersNextQuestion).toBe(false)
    })
})
