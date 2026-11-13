import { describe, expect, it } from "vitest"

import {
    answerOutcomeKey,
    formatScore,
    GRADE_SCALE,
    gradeOnScale,
    scoreTone,
} from "@/lib/grades"

describe("gradeOnScale", () => {
    it("rebases a score on the grade scale", () => {
        expect(GRADE_SCALE).toBe(20)
        expect(gradeOnScale(7.5, 15)).toBe(10)
        expect(gradeOnScale(3, 3)).toBe(20)
        expect(gradeOnScale(0, 8)).toBe(0)
    })

    it("has no grade for a paper without points", () => {
        expect(gradeOnScale(0, 0)).toBeNull()
        expect(gradeOnScale(2, -1)).toBeNull()
    })

    it("refuses non-finite values instead of showing NaN", () => {
        expect(gradeOnScale(Number.NaN, 10)).toBeNull()
        expect(gradeOnScale(5, Number.POSITIVE_INFINITY)).toBeNull()
    })
})

describe("formatScore", () => {
    it("keeps at most two decimals in the reader's locale", () => {
        expect(formatScore(12.3456, "en")).toBe("12.35")
        expect(formatScore(12.3456, "fr")).toBe("12,35")
        expect(formatScore(14, "fr")).toBe("14")
    })
})

describe("scoreTone", () => {
    it("tells full marks, partial credit and no credit apart", () => {
        expect(scoreTone(2, 2)).toBe("success")
        expect(scoreTone(0.5, 2)).toBe("warning")
        expect(scoreTone(0, 2)).toBe("destructive")
        expect(scoreTone(0, 0)).toBe("destructive")
    })
})

describe("answerOutcomeKey", () => {
    it("tells full, partial and no credit apart", () => {
        expect(answerOutcomeKey(2, 2)).toBe("training-correct")
        expect(answerOutcomeKey(0.5, 2)).toBe("answer-partially-correct")
        expect(answerOutcomeKey(0, 2)).toBe("training-incorrect")
    })
})
