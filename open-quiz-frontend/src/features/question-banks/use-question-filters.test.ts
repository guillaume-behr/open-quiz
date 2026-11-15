// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { Question } from "@/api/types"

import { useQuestionFilters } from "./use-question-filters"

function question(
    id: number,
    difficulty: Question["difficulty"],
    points: number[],
    answerMode: Question["answer_mode"] = "single"
): Question {
    return {
        id,
        difficulty,
        answer_mode: answerMode,
        choices: points.map((value) => ({ points: value })),
    } as Question
}

const questions = [
    question(1, "hard", [3]),
    question(2, "easy", [1, -2]),
    question(3, "medium", [2], "written"),
]
const ids = (list: Question[]) => list.map((item) => item.id)

describe("useQuestionFilters", () => {
    it("sorts by difficulty by default and can keep the bank order", () => {
        const { result } = renderHook(() => useQuestionFilters(questions))
        expect(ids(result.current.visibleQuestions)).toEqual([2, 3, 1])
        expect(result.current.activeCount).toBe(0)
        act(() => result.current.setSort("default"))
        expect(ids(result.current.visibleQuestions)).toEqual([1, 2, 3])
        act(() => result.current.setSort("points-desc"))
        expect(ids(result.current.visibleQuestions)).toEqual([1, 3, 2])
        act(() => result.current.setSort("difficulty-desc"))
        expect(ids(result.current.visibleQuestions)).toEqual([1, 3, 2])
        expect(result.current.activeCount).toBe(1)
        expect(result.current.hasFilters).toBe(false)
    })

    it("filters by points, difficulty and answer mode, then clears", () => {
        const { result } = renderHook(() =>
            useQuestionFilters(questions, { sort: "points-asc" })
        )
        act(() => result.current.setMinimumPoints("2"))
        expect(ids(result.current.visibleQuestions)).toEqual([3, 1])
        act(() => result.current.setMaximumDifficulty("medium"))
        expect(ids(result.current.visibleQuestions)).toEqual([3])
        act(() => result.current.toggleAnswerMode("single"))
        expect(ids(result.current.visibleQuestions)).toEqual([])
        expect(result.current.activeCount).toBe(4)
        act(() => result.current.toggleAnswerMode("single"))
        act(() => {
            result.current.setMaximumPoints("1")
            result.current.setMinimumDifficulty("easy")
        })
        expect(result.current.hasFilters).toBe(true)
        act(() => result.current.clearFilters())
        expect(result.current.hasFilters).toBe(false)
        expect(result.current.values.sort).toBe("points-asc")
        expect(ids(result.current.visibleQuestions)).toEqual([2, 3, 1])
    })
})
