// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type {
    QuizAnswerReview,
    QuizParticipant,
    QuizSession,
} from "@/api/types"

import { useWrittenAnswerGrading } from "./use-written-answer-grading"

const api = vi.hoisted(() => ({
    getParticipantAnswers: vi.fn(),
    gradeWrittenAnswer: vi.fn(),
}))
vi.mock("@/api/quizzes", () => api)

const answer = {
    id: 5,
    score: 0,
    max_score: 2,
    is_graded: false,
    feedback: null,
} as unknown as QuizAnswerReview
const participant = {
    id: 9,
    score: 3.1,
    pending_manual_grading_count: 1,
} as QuizParticipant
const otherParticipant = { ...participant, id: 10 }
const session = {
    id: 1,
    grades_published_at: null,
    participants: [participant, otherParticipant],
} as unknown as QuizSession

function renderGrading(result: QuizSession | null = session) {
    const onSessionGraded = vi.fn()
    const hook = renderHook(() =>
        useWrittenAnswerGrading(result, participant, onSessionGraded)
    )
    return { ...hook, onSessionGraded }
}

describe("useWrittenAnswerGrading", () => {
    beforeEach(() => {
        api.getParticipantAnswers.mockResolvedValue([answer])
        api.gradeWrittenAnswer.mockResolvedValue({
            ...answer,
            score: 1.25,
            is_graded: true,
        })
    })

    it("loads the answers and fills the drafts from them", async () => {
        const { result } = renderGrading()
        await waitFor(() => expect(result.current.answers).toEqual([answer]))
        expect(api.getParticipantAnswers).toHaveBeenCalledWith(1, 9)
        expect(result.current.scoreDrafts).toEqual({ 5: "0" })
        expect(result.current.feedbackDrafts).toEqual({ 5: "" })
        act(() => {
            result.current.setScoreDraft(5, "1")
            result.current.setFeedbackDraft(5, "ok")
        })
        expect(result.current.scoreDrafts).toEqual({ 5: "1" })
        expect(result.current.feedbackDrafts).toEqual({ 5: "ok" })
        act(() => result.current.reset())
        expect(result.current.scoreDrafts).toEqual({ 5: "0" })
    })

    it("refuses an empty or out-of-range score", async () => {
        const { result } = renderGrading()
        await waitFor(() => expect(result.current.answers).toHaveLength(1))
        for (const draft of ["", "3", "-1"]) {
            act(() => result.current.setScoreDraft(5, draft))
            await act(() => result.current.grade(answer))
            expect(result.current.error).toContain("score-out-of-range")
        }
        expect(api.gradeWrittenAnswer).not.toHaveBeenCalled()
    })

    it("saves a grade and updates the participant's score at once", async () => {
        const { result, onSessionGraded } = renderGrading()
        await waitFor(() => expect(result.current.answers).toHaveLength(1))
        act(() => {
            result.current.setScoreDraft(5, " 1.25 ")
            result.current.setFeedbackDraft(5, "good")
        })
        await act(() => result.current.grade(answer))
        expect(api.gradeWrittenAnswer).toHaveBeenCalledWith(1, 5, 1.25, "good")
        expect(result.current.answers[0]?.score).toBe(1.25)
        expect(result.current.gradingAnswerId).toBeNull()
        expect(result.current.error).toBeNull()

        const update = onSessionGraded.mock.calls[0]?.[0] as (
            value: QuizSession
        ) => QuizSession
        const updated = update(session)
        expect(updated.participants[0]).toMatchObject({
            score: 4.35,
            pending_manual_grading_count: 0,
        })
        expect(updated.participants[1]).toBe(otherParticipant)
        const other = { ...session, id: 2 }
        expect(update(other)).toBe(other)
    })

    it("reports a failed save and grades nothing once published", async () => {
        api.gradeWrittenAnswer.mockRejectedValue(new Error("down"))
        const { result } = renderGrading()
        await waitFor(() => expect(result.current.answers).toHaveLength(1))
        await act(() => result.current.grade(answer))
        expect(result.current.error).toBe("grade-answer-error")

        api.gradeWrittenAnswer.mockClear()
        const published = renderGrading({
            ...session,
            grades_published_at: "2026-01-01T00:00:00Z",
        })
        await act(() => published.result.current.grade(answer))
        expect(api.gradeWrittenAnswer).not.toHaveBeenCalled()
    })

    it("explains a failed load", async () => {
        api.getParticipantAnswers.mockRejectedValue(new Error("down"))
        const { result } = renderGrading()
        await waitFor(() =>
            expect(result.current.error).toBe("answers-load-error")
        )
    })
})
